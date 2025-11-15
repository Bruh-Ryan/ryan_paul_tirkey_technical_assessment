# slack.py

import json
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

# TODO: Replace with your actual HubSpot app credentials
CLIENT_ID = '754b1b62-5161-4b99-9fc4-6630ba346b48'
CLIENT_SECRET = 'e27f92f5-6fb3-4b38-ab98-3b006334cb12'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'

# HubSpot OAuth endpoints
AUTHORIZATION_URL = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'

# Scopes - common permissions for accessing HubSpot CRM data
SCOPES = 'crm.objects.contacts.read crm.objects.contacts.write crm.objects.companies.read crm.objects.deals.read'

async def authorize_hubspot(user_id, org_id):
    """
    Initiates the OAuth flow by creating an authorization URL and storing state in Redis.
    Returns the authorization URL for the user to visit.
    """
    # Create state data for CSRF protection
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    
    # Encode state as JSON string
    encoded_state = json.dumps(state_data)
    
    # Store state in Redis with 10 minute expiration
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', encoded_state, expire=600)
    
    # Build authorization URL
    auth_url = (
        f'{AUTHORIZATION_URL}'
        f'?client_id={CLIENT_ID}'
        f'&redirect_uri={REDIRECT_URI}'
        f'&scope={SCOPES}'
        f'&state={encoded_state}'
    )
    
    return auth_url


async def oauth2callback_hubspot(request: Request):
    """
    Handles the OAuth callback from HubSpot.
    Validates state, exchanges authorization code for tokens, and stores credentials in Redis.
    """
    # Check for errors in the callback
    if request.query_params.get('error'):
        raise HTTPException(
            status_code=400, 
            detail=request.query_params.get('error')
        )
    
    # Extract code and state from query parameters
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    
    # Parse state data
    state_data = json.loads(encoded_state)
    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')
    
    # Retrieve saved state from Redis
    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')
    
    # Validate state matches (CSRF protection)
    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')
    
    # Exchange authorization code for access token
    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI,
                    'code': code,
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )
    
    # Store credentials in Redis with 10 minute expiration
    await add_key_value_redis(
        f'hubspot_credentials:{org_id}:{user_id}', 
        json.dumps(response.json()), 
        expire=600
    )
    
    # JavaScript to close the OAuth popup window
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)


async def get_hubspot_credentials(user_id, org_id):
    """
    Retrieves stored HubSpot credentials from Redis.
    Returns the credentials as a JSON object.
    """
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    
    return json.loads(credentials)


async def create_integration_item_metadata_object(response_json):
    """
    Helper function to create IntegrationItem metadata from HubSpot API response.
    """
    # TODO: Customize based on the HubSpot data you're fetching
    return {}


async def get_items_hubspot(credentials):
    """
    Fetches contacts from HubSpot CRM using the stored credentials.
    Returns a list of IntegrationItem objects.
    """
    access_token = credentials.get('access_token')
    
    if not access_token:
        print("ERROR: No access token found in credentials")
        return []
    
    items = []
    
    try:
        async with httpx.AsyncClient() as client:
            # Fetch contacts from HubSpot CRM API
            response = await client.get(
                'https://api.hubapi.com/crm/v3/objects/contacts',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                },
                params={
                    'limit': 10,  # Get first 10 contacts
                    'properties': 'firstname,lastname,email,phone,company'
                }
            )
            
            if response.status_code != 200:
                print(f"ERROR: HubSpot API returned status {response.status_code}")
                print(f"Response: {response.text}")
                return []
            
            contacts_data = response.json()
            
            print(f"\n{'='*50}")
            print(f"HubSpot Contacts Retrieved")
            print(f"{'='*50}")
            print(f"Total contacts found: {len(contacts_data.get('results', []))}\n")
            
            for contact in contacts_data.get('results', []):
                properties = contact.get('properties', {})
                
                # Build full name
                firstname = properties.get('firstname', '')
                lastname = properties.get('lastname', '')
                name = f"{firstname} {lastname}".strip() or properties.get('email', 'Unknown Contact')
                
                # Create IntegrationItem object
                item = IntegrationItem(
                    id=contact.get('id'),
                    type='contact',
                    name=name,
                    creation_time=contact.get('createdAt'),
                    last_modified_time=contact.get('updatedAt'),
                    url=f"https://app.hubspot.com/contacts/{contact.get('id')}",
                    parent_path_or_name='HubSpot CRM'
                )
                items.append(item)
                
                # Print to console (as requested in assignment)
                print(f"Contact: {item.name}")
                print(f"  ID: {item.id}")
                print(f"  Email: {properties.get('email', 'N/A')}")
                print(f"  Phone: {properties.get('phone', 'N/A')}")
                print(f"  Company: {properties.get('company', 'N/A')}")
                print(f"  Created: {item.creation_time}")
                print(f"  Last Modified: {item.last_modified_time}")
                print(f"  URL: {item.url}")
                print(f"  {'-'*40}")
            
            print(f"\nTotal IntegrationItems created: {len(items)}")
            print(f"{'='*50}\n")
            
    except Exception as e:
        print(f"ERROR fetching HubSpot contacts: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return items


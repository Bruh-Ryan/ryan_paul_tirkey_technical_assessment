import { useState } from 'react';

import {
  Box,
  Autocomplete,
  TextField,
} from '@mui/material';

import { AirtableIntegration } from './integrations/airtable';
import { NotionIntegration } from './integrations/notion';
import { HubSpotIntegration } from './integrations/hubspot';  // Add this import
import { DataForm } from './data-form';

const integrationMapping = {
  'Notion': NotionIntegration,
  'Airtable': AirtableIntegration,
  'HubSpot': HubSpotIntegration,  // Add this line
};

export const IntegrationForm = () => {
  const [integrationParams, setIntegrationParams] = useState({});
  const [user, setUser] = useState('TestUser');
  const [org, setOrg] = useState('TestOrg');
  const [currType, setCurrType] = useState(null);
  const CurrIntegration = integrationMapping[currType];

  return (
    <Box>
      <TextField
        label="User"
        value={user}
        onChange={(e) => setUser(e.target.value)}
        sx={{mt: 2}}
      />
      <TextField
        label="Organization"
        value={org}
        onChange={(e) => setOrg(e.target.value)}
        sx={{mt: 2}}
      />
      <Autocomplete
        options={Object.keys(integrationMapping)}
        renderInput={(params) => <TextField {...params} label="Integration" />}
        onChange={(e, value) => setCurrType(value)}
      />
      {currType && 
        <CurrIntegration 
          user={user} 
          org={org} 
          integrationParams={integrationParams} 
          setIntegrationParams={setIntegrationParams}
        />
      }
      {integrationParams?.credentials &&
        <DataForm integrationParams={integrationParams}/>
      }
    </Box>
  );
};

// frontend/src/app/register/page.tsx
'use client';

import React, { useState } from 'react';
import {
  Box,
  TextField,
  Button,
  Typography,
  Container,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  OutlinedInput,
  Checkbox,
  ListItemText
} from '@mui/material';
import { useAuth } from '../../context/AuthContext';
import { useRouter } from 'next/navigation';

const ITEM_HEIGHT = 48;
const ITEM_PADDING_TOP = 8;
const MenuProps = {
  PaperProps: {
    style: {
      maxHeight: ITEM_HEIGHT * 4.5 + ITEM_PADDING_TOP,
      width: 250,
    },
  },
};

const availablePermissionGroups = ['all_users', 'dev_team', 'hr_team', 'legal_team'];

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [permissionGroups, setPermissionGroups] = useState<string[]>(['all_users']);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const { register, loading } = useAuth();
  const router = useRouter();

  const getErrorMessage = (err: unknown, fallbackMessage: string): string => {
    if (err instanceof Error && err.message) {
      return err.message;
    }

    if (typeof err === 'object' && err !== null && 'response' in err) {
      const errorWithResponse = err as { response?: { data?: { detail?: string } } };
      return errorWithResponse.response?.data?.detail ?? fallbackMessage;
    }

    return fallbackMessage;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    try {
      await register(username, password, permissionGroups);
      setSuccess('Registration successful! You can now log in.');
      router.push('/login');
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Registration failed.'));
    }
  };

  return (
    <Container component="main" maxWidth="xs">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Typography component="h1" variant="h5">
          Register
        </Typography>
        <Box component="form" onSubmit={handleSubmit} noValidate sx={{ mt: 1 }}>
          {error && <Alert severity="error" sx={{ width: '100%', mb: 2 }}>{error}</Alert>}
          {success && <Alert severity="success" sx={{ width: '100%', mb: 2 }}>{success}</Alert>}
          <TextField
            margin="normal"
            required
            fullWidth
            id="username"
            label="Username"
            name="username"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label="Password"
            type="password"
            id="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="confirmPassword"
            label="Confirm Password"
            type="password"
            id="confirmPassword"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <FormControl fullWidth margin="normal">
            <InputLabel id="permission-groups-label">Permission Groups</InputLabel>
            <Select
              labelId="permission-groups-label"
              id="permission-groups"
              multiple
              value={permissionGroups}
              onChange={(e) => setPermissionGroups(e.target.value as string[])}
              input={<OutlinedInput label="Permission Groups" />}
              renderValue={(selected) => selected.join(', ')}
              MenuProps={MenuProps}
            >
              {availablePermissionGroups.map((group) => (
                <MenuItem key={group} value={group}>
                  <Checkbox checked={permissionGroups.indexOf(group) > -1} />
                  <ListItemText primary={group} />
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading}
          >
            {loading ? 'Registering...' : 'Register'}
          </Button>
          <Button
            fullWidth
            variant="text"
            onClick={() => router.push('/login')}
          >
            Already have an account? Sign In
          </Button>
        </Box>
      </Box>
    </Container>
  );
}

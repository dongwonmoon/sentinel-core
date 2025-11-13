// frontend/src/components/ConversationSidebar.tsx
'use client';

import React from 'react';
import {
  Box,
  Toolbar,
  Typography,
  Divider,
  List,
  ListItemText,
  IconButton,
  Button,
  ListItemButton,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import LogoutIcon from '@mui/icons-material/Logout';
import MenuIcon from '@mui/icons-material/Menu';
import { useAuth } from '../context/AuthContext';

interface ConversationSidebarProps {
  onNewChat: () => void;
  handleDrawerToggle: () => void;
  drawerWidth: number;
}

export default function ConversationSidebar({ onNewChat, handleDrawerToggle, drawerWidth }: ConversationSidebarProps) {
  const { user, logout } = useAuth();

  // Placeholder for conversation sessions
  const conversationSessions = [
    { id: '1', title: '휴가 정책 질문', date: '오늘' },
    { id: '2', title: '코드 리팩토링', date: '어제' },
  ];

  return (
    <Box sx={{ overflow: 'auto', height: '100%' }}>
      <Toolbar sx={{ justifyContent: 'space-between' }}>
        <Typography variant="h6" noWrap component="div">
          Sentinel-Core
        </Typography>
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={handleDrawerToggle}
          sx={{ mr: 2, display: { sm: 'none' } }}
        >
          <MenuIcon />
        </IconButton>
      </Toolbar>
      <Divider />
      <List>
        <ListItemButton>
          <Button
            variant="contained"
            color="primary"
            fullWidth
            startIcon={<AddIcon />}
            onClick={onNewChat}
          >
            New Chat
          </Button>
        </ListItemButton>
      </List>
      <Divider />
      <List>
        {conversationSessions.map((session) => (
          <ListItemButton key={session.id}>
            <ChatBubbleOutlineIcon sx={{ mr: 2 }} />
            <ListItemText primary={session.title} secondary={session.date} />
          </ListItemButton>
        ))}
      </List>
      <Box sx={{ position: 'absolute', bottom: 0, width: `calc(${drawerWidth}px - 16px)`, p: 2 }}>
        <Divider sx={{ mb: 1 }} />
        <ListItemButton onClick={logout}>
          <LogoutIcon sx={{ mr: 2 }} />
          <ListItemText primary={`Logout (${user?.username || 'User'})`} />
        </ListItemButton>
      </Box>
    </Box>
  );
}

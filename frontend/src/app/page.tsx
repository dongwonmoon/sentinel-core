// frontend/src/app/page.tsx
'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Drawer,
  TextField,
  Button,
  Paper,
  CircularProgress,
  Alert,
  InputAdornment,
  Menu,
  MenuItem,
  Fab,
  List,
  ListItem,
  ListItemText,
  Snackbar,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import AddIcon from '@mui/icons-material/Add';
import SendIcon from '@mui/icons-material/Send';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import GitHubIcon from '@mui/icons-material/GitHub';
import { useAuth } from '../context/AuthContext';
import api, { ChatMessage, Source } from '../lib/api';
import ConversationSidebar from '../components/ConversationSidebar';
import ContextSelectorModal from '../components/ContextSelectorModal';

const drawerWidth = 280;

export default function HomePage() {
  const { user, loading: authLoading } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSources, setCurrentSources] = useState<Source[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

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

  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({
    open: false,
    message: '',
    severity: 'info',
  });

  const [uploadAnchorEl, setUploadAnchorEl] = useState<null | HTMLElement>(null);
  const uploadMenuOpen = Boolean(uploadAnchorEl);

  const [contextModalOpen, setContextModalOpen] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [contextButtonText, setContextButtonText] = useState('Context: All Documents');

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleUploadMenuClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setUploadAnchorEl(event.currentTarget);
  };

  const handleUploadMenuClose = () => {
    setUploadAnchorEl(null);
  };

  const handleFileUploadClick = () => {
    fileInputRef.current?.click();
    handleUploadMenuClose();
  };

  const handleFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setSnackbar({ open: true, message: `Uploading ${file.name}...`, severity: 'info' });
    try {
      const response = await api.uploadFile(file);
      setSnackbar({ open: true, message: response.message, severity: 'success' });
    } catch (err: unknown) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, 'File upload failed.'),
        severity: 'error',
      });
    }
  };

  const handleGithubIndex = async () => {
    handleUploadMenuClose();
    const repoUrl = window.prompt('Enter the GitHub repository URL to index:');
    if (!repoUrl) return;

    setSnackbar({ open: true, message: `Indexing ${repoUrl}...`, severity: 'info' });
    try {
      const response = await api.indexGithubRepo(repoUrl);
      setSnackbar({ open: true, message: response.message, severity: 'success' });
    } catch (err: unknown) {
      setSnackbar({
        open: true,
        message: getErrorMessage(err, 'GitHub indexing failed.'),
        severity: 'error',
      });
    }
  };
  
  const handleNewChat = () => {
    setMessages([]);
    setCurrentSources([]);
    setError(null);
  };

  const handleContextModalOpen = () => setContextModalOpen(true);
  const handleContextModalClose = () => setContextModalOpen(false);

  const handleSaveContext = (newSelectedDocIds: string[]) => {
    setSelectedDocIds(newSelectedDocIds);
    if (newSelectedDocIds.length === 0) {
      setContextButtonText('Context: All Documents');
    } else if (newSelectedDocIds.length === 1) {
      setContextButtonText(`Context: 1 Document`);
    } else {
      setContextButtonText(`Context: ${newSelectedDocIds.length} Documents`);
    }
    handleContextModalClose();
  };

  // Cleanup effect for EventSource
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (user) {
      api.getChatHistory()
        .then(history => {
          setMessages(history.messages.map(msg => ({ role: msg.role, content: msg.content })));
        })
        .catch(err => {
          console.error('Failed to fetch chat history:', err);
          setError(getErrorMessage(err, 'Failed to load chat history.'));
        });
    }
  }, [user]);

  const handleSendMessage = (event: React.FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim() || isStreaming) return;

    const userMessage: ChatMessage = { role: 'user', content: inputMessage };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setInputMessage('');
    setError(null);
    setIsStreaming(true);
    setCurrentSources([]);

    try {
      const eventSource = api.queryAgent(
        {
          query: userMessage.content,
          chat_history: updatedMessages,
          doc_ids_filter: selectedDocIds.length > 0 ? selectedDocIds : undefined,
        },
        (event) => { // onMessage
          const parsedData = JSON.parse(event.data);
          const sseEvent = parsedData.event;

          if (sseEvent === 'token') {
            const token = parsedData.data;
            setMessages(prev => {
              const lastMessage = prev[prev.length - 1];
              if (lastMessage && lastMessage.role === 'assistant') {
                const newMessages = [...prev];
                newMessages[newMessages.length - 1] = { ...lastMessage, content: lastMessage.content + token };
                return newMessages;
              } else {
                return [...prev, { role: 'assistant', content: token }];
              }
            });
          } else if (sseEvent === 'sources') {
            setCurrentSources(parsedData.data as Source[]);
          } else if (sseEvent === 'end') {
            setIsStreaming(false);
            eventSourceRef.current?.close();
          }
        },
        (errorEvent) => { // onError
          console.error('SSE Error:', errorEvent);
          setError('An error occurred during streaming. Please try again.');
          setIsStreaming(false);
          eventSourceRef.current?.close();
        },
        () => { // onClose (This is now effectively handled by the 'end' event)
          setIsStreaming(false);
          eventSourceRef.current?.close();
        }
      );
      eventSourceRef.current = eventSource;

    } catch (err: unknown) {
      console.error('API Query Error:', err);
      setError(getErrorMessage(err, 'Failed to get response from agent.'));
      setIsStreaming(false);
    }
  };

  if (authLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelected}
        style={{ display: 'none' }}
      />
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
          zIndex: (theme) => theme.zIndex.drawer + 1,
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            Sentinel-Core RAG
          </Typography>
          <Button variant="contained" color="secondary" onClick={handleContextModalOpen}>
            {contextButtonText}
          </Button>
        </Toolbar>
      </AppBar>
      <Box
        component="nav"
        sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}
        aria-label="conversation folders"
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          <ConversationSidebar onNewChat={handleNewChat} handleDrawerToggle={handleDrawerToggle} drawerWidth={drawerWidth} />
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          <ConversationSidebar onNewChat={handleNewChat} handleDrawerToggle={handleDrawerToggle} drawerWidth={drawerWidth} />
        </Drawer>
      </Box>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
        }}
      >
        <Toolbar />
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box sx={{ flexGrow: 1, overflowY: 'auto', mb: 2 }}>
          {messages.map((msg, index) => (
            <Box
              key={index}
              sx={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                mb: 2,
              }}
            >
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  maxWidth: '70%',
                  bgcolor: msg.role === 'user' ? 'primary.light' : 'grey.200',
                  color: msg.role === 'user' ? 'white' : 'text.primary',
                  borderRadius: msg.role === 'user' ? '20px 20px 5px 20px' : '20px 20px 20px 5px',
                }}
              >
                <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>{msg.content}</Typography>
                {msg.role === 'assistant' && currentSources.length > 0 && index === messages.length - 1 && (
                  <Box sx={{ mt: 1, fontSize: '0.8rem', color: 'text.secondary' }}>
                    <Typography variant="caption">Sources:</Typography>
                    <List dense disablePadding>
                      {currentSources.map((source, srcIndex) => (
                        <ListItem key={srcIndex} disablePadding>
                          <ListItemText primary={`${source.metadata.source} (Score: ${source.score.toFixed(2)})`} />
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                )}
              </Paper>
            </Box>
          ))}
          <div ref={messagesEndRef} />
        </Box>
        <Box component="form" onSubmit={handleSendMessage} sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <IconButton
            color="primary"
            aria-label="upload new knowledge"
            onClick={handleUploadMenuClick}
            disabled={isStreaming}
          >
            <AddIcon />
          </IconButton>
          <Menu
            anchorEl={uploadAnchorEl}
            open={uploadMenuOpen}
            onClose={handleUploadMenuClose}
          >
            <MenuItem onClick={handleFileUploadClick}>
              <UploadFileIcon sx={{ mr: 1 }} /> Upload File
            </MenuItem>
            <MenuItem onClick={handleGithubIndex}>
              <GitHubIcon sx={{ mr: 1 }} /> Index GitHub Repo
            </MenuItem>
          </Menu>

          <TextField
            fullWidth
            variant="outlined"
            placeholder="Ask Sentinel-Core..."
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                handleSendMessage(e);
              }
            }}
            disabled={isStreaming}
            sx={{ '& .MuiOutlinedInput-root': { borderRadius: '25px', pr: 0.5 } }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Fab
                    color="primary"
                    size="small"
                    type="submit"
                    disabled={!inputMessage.trim() || isStreaming}
                    sx={{ boxShadow: 'none' }}
                  >
                    {isStreaming ? <CircularProgress size={20} color="inherit" /> : <SendIcon />}
                  </Fab>
                </InputAdornment>
              ),
            }}
          />
        </Box>
      </Box>
      <ContextSelectorModal
        open={contextModalOpen}
        onClose={handleContextModalClose}
        onSave={handleSaveContext}
        initialSelectedDocIds={selectedDocIds}
      />
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setSnackbar({ ...snackbar, open: false })} severity={snackbar.severity} sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}

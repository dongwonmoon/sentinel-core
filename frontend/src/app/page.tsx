// frontend/src/app/page/page.tsx
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
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import AddIcon from '@mui/icons-material/Add';
import SendIcon from '@mui/icons-material/Send';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import GitHubIcon from '@mui/icons-material/GitHub';
import { useAuth } from '../context/AuthContext';
import api, { ChatMessage, ChatMessageRole, Source } from '../lib/api';
import ConversationSidebar from '../components/ConversationSidebar';
import ContextSelectorModal from '../components/ContextSelectorModal';

const drawerWidth = 280;

export default function HomePage() {
  const { user, logout, loading: authLoading } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSources, setCurrentSources] = useState<Source[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Upload menu state
  const [uploadAnchorEl, setUploadAnchorEl] = useState<null | HTMLElement>(null);
  const uploadMenuOpen = Boolean(uploadAnchorEl);

  // Context selector modal state
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

  const handleFileUpload = () => {
    // TODO: Implement file upload logic
    alert('File upload not yet implemented!');
    handleUploadMenuClose();
  };

  const handleGithubIndex = () => {
    // TODO: Implement GitHub indexing logic
    alert('GitHub indexing not yet implemented!');
    handleUploadMenuClose();
  };

  const handleContextModalOpen = () => {
    setContextModalOpen(true);
  };

  const handleContextModalClose = () => {
    setContextModalOpen(false);
  };

  const handleSaveContext = (newSelectedDocIds: string[]) => {
    setSelectedDocIds(newSelectedDocIds);
    if (newSelectedDocIds.length === 0) {
      setContextButtonText('Context: None');
    } else if (newSelectedDocIds.length === 1) {
      setContextButtonText(`Context: 1 Document`);
    } else {
      setContextButtonText(`Context: ${newSelectedDocIds.length} Documents`);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (user) {
      api.getChatHistory().then(history => {
        setMessages(history.messages.map(msg => ({ role: msg.role, content: msg.content })));
      }).catch(err => {
        console.error("Failed to fetch chat history:", err);
        setError("Failed to load chat history.");
      });
    }
  }, [user]);

  const handleSendMessage = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim() || isStreaming) return;

    const userMessage: ChatMessage = { role: 'user', content: inputMessage };
    setMessages((prevMessages) => [...prevMessages, userMessage]);
    setInputMessage('');
    setError(null);
    setIsStreaming(true);
    setCurrentSources([]); // Clear sources for new query

    let fullAssistantResponse = '';
    let assistantMessageIndex = -1;

    try {
      await api.queryAgent(
        {
          query: userMessage.content,
          chat_history: messages,
          doc_ids_filter: selectedDocIds.length > 0 ? selectedDocIds : undefined,
        },
        (event) => {
          const data = JSON.parse(event.data);
          if (data.event === 'token') {
            const token = data.data;
            if (assistantMessageIndex === -1) {
              assistantMessageIndex = messages.length; // Index of the new assistant message
              setMessages((prev) => {
                const newMsg: ChatMessage = { role: 'assistant', content: token };
                return [...prev, newMsg];
              });
            } else {
              setMessages((prev) => {
                const newMessages = [...prev];
                newMessages[assistantMessageIndex].content += token;
                return newMessages;
              });
            }
            fullAssistantResponse += token;
          } else if (data.event === 'sources') {
            setCurrentSources(data.data);
          } else if (data.event === 'end') {
            setIsStreaming(false);
          }
        },
        (errorEvent) => {
          console.error('SSE Error:', errorEvent);
          setError('An error occurred during streaming. Please try again.');
          setIsStreaming(false);
        },
        () => {
          setIsStreaming(false);
        }
      );
    } catch (err: any) {
      console.error('API Query Error:', err);
      setError(err.message || 'Failed to get response from agent.');
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
          {/* Context Selector Button */}
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
        {/* Mobile Drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          <ConversationSidebar mobileOpen={mobileOpen} handleDrawerToggle={handleDrawerToggle} drawerWidth={drawerWidth} />
        </Drawer>
        {/* Desktop Drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          <ConversationSidebar mobileOpen={mobileOpen} handleDrawerToggle={handleDrawerToggle} drawerWidth={drawerWidth} />
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
        <Toolbar /> {/* Spacer for AppBar */}
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
                <Typography variant="body1">{msg.content}</Typography>
                {msg.role === 'assistant' && currentSources.length > 0 && (
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
          {/* Upload Button */}
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
            MenuListProps={{
              'aria-labelledby': 'upload-button',
            }}
          >
            <MenuItem onClick={handleFileUpload}>
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
            sx={{
              '& .MuiOutlinedInput-root': {
                borderRadius: '25px',
                pr: 0.5,
              },
            }}
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
    </Box>
  );
}

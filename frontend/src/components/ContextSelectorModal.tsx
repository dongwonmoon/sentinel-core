// frontend/src/components/ContextSelectorModal.tsx
'use client';

import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
  ListItemText,
  Checkbox,
  FormControlLabel,
  CircularProgress,
  Alert,
  Box,
  Typography,
} from '@mui/material';
import api, { DocumentItem } from '../lib/api';

interface ContextSelectorModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (selectedDocIds: string[]) => void;
  initialSelectedDocIds: string[];
}

export default function ContextSelectorModal({
  open,
  onClose,
  onSave,
  initialSelectedDocIds,
}: ContextSelectorModalProps) {
  const [availableDocuments, setAvailableDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>(initialSelectedDocIds);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLoading(true);
      setError(null);
      api.getDocuments()
        .then(data => {
          const docs: DocumentItem[] = Object.entries(data).map(([key, value]) => ({
            filter_key: key,
            display_name: value,
          }));
          setAvailableDocuments(docs);
          setSelectedDocuments(initialSelectedDocIds); // Reset selection on open
        })
        .catch(err => {
          console.error("Failed to fetch documents:", err);
          setError('Failed to load available documents.');
        })
        .finally(() => setLoading(false));
    }
  }, [open, initialSelectedDocIds]);

  const handleToggle = (docId: string) => () => {
    const currentIndex = selectedDocuments.indexOf(docId);
    const newSelected = [...selectedDocuments];

    if (currentIndex === -1) {
      newSelected.push(docId);
    } else {
      newSelected.splice(currentIndex, 1);
    }
    setSelectedDocuments(newSelected);
  };

  const handleSave = () => {
    onSave(selectedDocuments);
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Select Context Documents</DialogTitle>
      <DialogContent dividers>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : availableDocuments.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No documents available. Please upload or index some knowledge sources.
          </Typography>
        ) : (
          <List dense>
            {availableDocuments.map((doc) => (
              <ListItem key={doc.filter_key} disablePadding>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={selectedDocuments.indexOf(doc.filter_key) !== -1}
                      onChange={handleToggle(doc.filter_key)}
                      edge="start"
                      tabIndex={-1}
                      disableRipple
                    />
                  }
                  label={doc.display_name}
                />
              </ListItem>
            ))}
          </List>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} variant="contained" disabled={loading}>
          Save Selection
        </Button>
      </DialogActions>
    </Dialog>
  );
}

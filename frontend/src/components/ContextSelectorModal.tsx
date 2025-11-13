// frontend/src/components/ContextSelectorModal.tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
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

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDocuments();
      const docs: DocumentItem[] = Object.entries(data).map(([key, value]) => ({
        filter_key: key,
        display_name: value,
      }));
      setAvailableDocuments(docs);
      setSelectedDocuments(initialSelectedDocIds);
    } catch (err: unknown) {
      console.error('Failed to fetch documents:', err);
      setError('Failed to load available documents.');
    } finally {
      setLoading(false);
    }
  }, [initialSelectedDocIds]);

  useEffect(() => {
    if (open) {
      void fetchDocuments();
    }
  }, [fetchDocuments, open]);

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

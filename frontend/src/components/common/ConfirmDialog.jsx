import React from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
} from '@mui/material'

/**
 * Reusable confirmation dialog for destructive actions.
 * @param {object} props
 * @param {boolean} props.open - Whether the dialog is open
 * @param {string} props.title - Dialog title
 * @param {string} props.message - Dialog body message
 * @param {function} props.onConfirm - Called when user clicks "Confirm"
 * @param {function} props.onCancel - Called when user dismisses the dialog
 * @param {string} [props.confirmLabel] - Label for confirm button (default "Confirm")
 * @param {string} [props.cancelLabel] - Label for cancel button (default "Cancel")
 * @param {string} [props.confirmColor] - MUI color for confirm button (default "error")
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmColor = 'error',
}) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{message}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} color="inherit">
          {cancelLabel}
        </Button>
        <Button onClick={onConfirm} color={confirmColor} variant="contained" autoFocus>
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

import React, { useState, useRef, useCallback, useEffect } from 'react'
import {
  Box,
  TextField,
  Typography,
  Chip,
  Divider,
  Paper,
  CircularProgress,
  Button,
  FormControlLabel,
  Checkbox,
  Alert,
  Stack,
} from '@mui/material'
import { createRoomsFromList } from '../../api/admin'
import { getErrorMessage } from '../../utils/errors'

/**
 * Textarea accepting comma-separated room entries (e.g. "201, 202, 203:3"),
 * debounced dry-run preview, capacity selector, and confirm create button.
 */
export default function RoomListInput({ floorId, onCreated }) {
  const [value, setValue] = useState('')
  const [capacity, setCapacity] = useState(2)
  const [skipExisting, setSkipExisting] = useState(true)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [resultMsg, setResultMsg] = useState(null)
  const [errorMsg, setErrorMsg] = useState(null)
  const debounceRef = useRef(null)

  const runDryRun = useCallback(
    async (text, cap) => {
      if (!floorId || !text.trim()) {
        setPreview(null)
        return
      }
      setLoading(true)
      setErrorMsg(null)
      try {
        const res = await createRoomsFromList(floorId, text, {
          capacity: Number(cap) || 2,
          skipExisting: true,
          dryRun: true,
        })
        setPreview(res)
      } catch (err) {
        setErrorMsg(getErrorMessage(err))
        setPreview(null)
      } finally {
        setLoading(false)
      }
    },
    [floorId]
  )

  useEffect(() => {
    if (value.trim() && floorId) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => runDryRun(value, capacity), 350)
    } else {
      setPreview(null)
    }
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [value, capacity, floorId, runDryRun])

  const handleSubmit = async () => {
    if (!floorId || !value.trim()) return
    setSubmitting(true)
    setErrorMsg(null)
    setResultMsg(null)
    try {
      const res = await createRoomsFromList(floorId, value, {
        capacity: Number(capacity) || 2,
        skipExisting,
        dryRun: false,
      })
      setResultMsg(`Created ${res.created ?? 0} room(s) on this floor.`)
      setValue('')
      setPreview(null)
      onCreated?.(res)
    } catch (err) {
      setErrorMsg(getErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const sections = [
    { key: 'to_create', label: 'Will be created', color: 'success' },
    { key: 'already_exist', label: 'Already exist', color: 'default' },
    { key: 'duplicates_in_input', label: 'Duplicates in input', color: 'warning' },
    { key: 'invalid', label: 'Invalid', color: 'error' },
  ]

  const canCreate = Boolean(floorId && value.trim() && !submitting && (preview?.to_create?.length ?? 0) > 0)

  return (
    <Box>
      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}
      {resultMsg && <Alert severity="success" sx={{ mb: 2 }}>{resultMsg}</Alert>}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
        <TextField
          label="Room numbers (comma-separated, optional room:capacity)"
          placeholder="e.g. 201, 202, 203:3, 204"
          multiline
          minRows={3}
          fullWidth
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setResultMsg(null)
          }}
          disabled={!floorId}
          helperText="Up to 200 rooms per batch. Append :N to override default capacity (e.g. 203:3)."
        />
        <TextField
          label="Default Capacity"
          type="number"
          size="small"
          inputProps={{ min: 1, max: 8 }}
          value={capacity}
          onChange={(e) => setCapacity(e.target.value)}
          sx={{ width: { xs: '100%', sm: 160 } }}
        />
      </Stack>

      <Box sx={{ mt: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
        <FormControlLabel
          control={
            <Checkbox
              checked={skipExisting}
              onChange={(e) => setSkipExisting(e.target.checked)}
              size="small"
            />
          }
          label={<Typography variant="body2">Skip already existing / invalid tokens on create</Typography>}
        />
        <Button variant="contained" disabled={!canCreate} onClick={handleSubmit}>
          {submitting ? 'Creating…' : `Create ${preview?.to_create?.length || 0} Room(s)`}
        </Button>
      </Box>

      {loading && (
        <Box sx={{ mt: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={16} />
          <Typography variant="caption" color="text.secondary">Validating…</Typography>
        </Box>
      )}

      {preview && !loading && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>Dry-run preview</Typography>
          <Divider sx={{ mb: 1.5 }} />
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {sections.map(({ key, label, color }) => {
              const items = preview[key] ?? []
              if (items.length === 0) return null
              return (
                <Box key={key}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    {label} ({items.length})
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                    {items.map((r) => (
                      <Chip
                        key={r}
                        label={r}
                        size="small"
                        color={color}
                        variant={color === 'default' ? 'outlined' : 'filled'}
                      />
                    ))}
                  </Box>
                </Box>
              )
            })}
          </Box>
        </Paper>
      )}
    </Box>
  )
}

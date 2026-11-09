import React, { useState } from 'react'
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TextField, Chip, Button, Alert,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listWardenStudents, verifyAccessibility } from '../../api/admin'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import { getErrorMessage } from '../../utils/errors'

export default function AccessibilityQueuePage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [note, setNote] = useState('')
  const [mutError, setMutError] = useState(null)

  const { data: students = [], isLoading, error } = useQuery({
    queryKey: ['warden-students', search],
    queryFn: () => listWardenStudents({ search: search || undefined, limit: 100 }),
  })

  const verifyMut = useMutation({
    mutationFn: ({ userId, verified }) =>
      verifyAccessibility(userId, { verified, note }),
    onSuccess: () => {
      setMutError(null)
      qc.invalidateQueries({ queryKey: ['warden-students'] })
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={1}>Accessibility Queue</Typography>
      <Typography color="text.secondary" mb={3}>
        Verify students with documented accessibility needs in your managed hostels. Verified students receive Tier-0 priority placement.
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{getErrorMessage(error)}</Alert>}
      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      <Box display="flex" gap={2} mb={2} flexWrap="wrap">
        <TextField
          label="Search student (name, roll no, or email)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          size="small"
          sx={{ minWidth: 300 }}
        />
        <TextField
          label="Verification note (audit log)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          size="small"
          sx={{ minWidth: 280 }}
        />
      </Box>

      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <TableContainer component={Paper} elevation={2}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><strong>Name</strong></TableCell>
                <TableCell><strong>Roll No</strong></TableCell>
                <TableCell><strong>Email</strong></TableCell>
                <TableCell><strong>Accessibility Status</strong></TableCell>
                <TableCell><strong>Action</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {students.map((s) => (
                <TableRow key={s._id} hover>
                  <TableCell>{s.name}</TableCell>
                  <TableCell>{s.roll_no || '—'}</TableCell>
                  <TableCell>{s.email}</TableCell>
                  <TableCell>
                    <Chip
                      label={s.accessibility_verified ? 'Verified (Tier 0)' : 'Standard (Tier 1)'}
                      color={s.accessibility_verified ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      size="small"
                      variant={s.accessibility_verified ? 'outlined' : 'contained'}
                      color={s.accessibility_verified ? 'warning' : 'success'}
                      disabled={verifyMut.isPending}
                      onClick={() =>
                        verifyMut.mutate({ userId: s._id, verified: !s.accessibility_verified })
                      }
                    >
                      {s.accessibility_verified ? 'Revoke' : 'Verify Accessibility'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {students.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ color: 'text.secondary' }}>
                    No students found in your managed hostels.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}

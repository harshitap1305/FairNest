import React, { useState } from 'react'
import {
  Box, Typography, MenuItem, TextField, Button, Card, CardContent,
  Alert, Table, TableBody, TableCell, TableRow, Paper, Chip,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import { useQuery, useMutation } from '@tanstack/react-query'
import { listCycles, verifyCycle } from '../../api/cycle'
import { getErrorMessage } from '../../utils/errors'

export default function VerifyAllocationPage() {
  const [cycleId, setCycleId] = useState('')
  const [result, setResult] = useState(null)

  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const verifiableCycles = (cycles || []).filter((c) =>
    ['ALLOTMENT_ACTIVE', 'CLOSED', 'SETTLED'].includes(c.status)
  )

  const verifyMut = useMutation({
    mutationFn: () => verifyCycle(cycleId),
    onSuccess: (res) => setResult(res),
    onError: (e) => setResult({ ok: false, error: getErrorMessage(e) }),
  })

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={1}>Verify Allocation Integrity</Typography>
      <Typography color="text.secondary" mb={3}>
        Independently recompute the Round-1 allocation from revealed seed and frozen application inputs, checking commitment, input hash, and output hash.
      </Typography>

      <Box display="flex" gap={2} alignItems="flex-end" mb={3}>
        <TextField
          select
          label="Select Cycle"
          value={cycleId}
          onChange={(e) => { setCycleId(e.target.value); setResult(null) }}
          size="small"
          sx={{ minWidth: 320 }}
        >
          {verifiableCycles.map((c) => (
            <MenuItem key={c._id} value={c._id}>{c.name} ({c.status})</MenuItem>
          ))}
        </TextField>
        <Button
          variant="contained"
          disabled={!cycleId || verifyMut.isPending}
          onClick={() => verifyMut.mutate()}
        >
          {verifyMut.isPending ? 'Verifying…' : 'Verify'}
        </Button>
      </Box>

      {result && (
        <Card elevation={2}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={3}>
              {result.ok ? (
                <>
                  <CheckCircleIcon color="success" sx={{ fontSize: 40 }} />
                  <Typography variant="h5" color="success.main" fontWeight={700}>
                    Verification PASSED
                  </Typography>
                </>
              ) : (
                <>
                  <CancelIcon color="error" sx={{ fontSize: 40 }} />
                  <Typography variant="h5" color="error.main" fontWeight={700}>
                    Verification FAILED
                  </Typography>
                </>
              )}
            </Box>

            {result.error && <Alert severity="error" sx={{ mb: 2 }}>{result.error}</Alert>}

            {result.checks && (
              <Table size="small" component={Paper} variant="outlined">
                <TableBody>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600 }}>Seed Commitment</TableCell>
                    <TableCell>
                      <Chip
                        label={result.checks.seed_ok ? 'PASS' : 'FAIL'}
                        color={result.checks.seed_ok ? 'success' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600 }}>Input Hash Integrity</TableCell>
                    <TableCell>
                      <Chip
                        label={result.checks.input_ok ? 'PASS' : 'FAIL'}
                        color={result.checks.input_ok ? 'success' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600 }}>Round-1 Output Hash</TableCell>
                    <TableCell>
                      <Chip
                        label={result.checks.output_ok ? 'PASS' : 'FAIL'}
                        color={result.checks.output_ok ? 'success' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                  {result.seed_commitment && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Seed Commitment</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.72rem', wordBreak: 'break-all' }}>
                        {result.seed_commitment}
                      </TableCell>
                    </TableRow>
                  )}
                  {result.seed_revealed && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Seed Revealed</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.72rem', wordBreak: 'break-all' }}>
                        {result.seed_revealed}
                      </TableCell>
                    </TableRow>
                  )}
                  {result.computed_input_hash && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Input Hash (stored / computed)</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.72rem', wordBreak: 'break-all' }}>
                        {result.stored_input_hash} / {result.computed_input_hash}
                      </TableCell>
                    </TableRow>
                  )}
                  {result.computed_output_hash && (
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>Output Hash (stored / computed)</TableCell>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.72rem', wordBreak: 'break-all' }}>
                        {result.stored_output_hash} / {result.computed_output_hash}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </Box>
  )
}

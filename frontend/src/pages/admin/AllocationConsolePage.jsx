import React, { useState } from 'react'
import {
  Box, Typography, Button, Card, CardContent, Alert, Stepper,
  Step, StepLabel, Chip, Table, TableBody, TableCell, TableRow, Paper,
} from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listCycles, previewAllocation, runAllocation, runCascade } from '../../api/cycle'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import { getErrorMessage } from '../../utils/errors'

const STEPS = ['Select Cycle', 'Preview', 'Run Allocation', 'Cascade (if needed)']

export default function AllocationConsolePage() {
  const qc = useQueryClient()
  const [selectedCycle, setSelectedCycle] = useState(null)
  const [activeStep, setActiveStep] = useState(0)
  const [preview, setPreview] = useState(null)
  const [runResult, setRunResult] = useState(null)
  const [cascadeResult, setCascadeResult] = useState(null)
  const [confirmRun, setConfirmRun] = useState(false)
  const [mutError, setMutError] = useState(null)

  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const readyCycles = (cycles || []).filter((c) => c.status === 'APPLICATIONS_CLOSED')

  const previewMut = useMutation({
    mutationFn: () => previewAllocation(selectedCycle._id),
    onSuccess: (res) => { setPreview(res); setActiveStep(1); setMutError(null) },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const runMut = useMutation({
    mutationFn: () => runAllocation(selectedCycle._id),
    onSuccess: (res) => {
      setRunResult(res)
      setActiveStep(2)
      qc.invalidateQueries({ queryKey: ['cycles'] })
      setMutError(null)
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  const cascadeMut = useMutation({
    mutationFn: () => runCascade(selectedCycle._id),
    onSuccess: (res) => {
      setCascadeResult(res)
      setActiveStep(3)
      qc.invalidateQueries({ queryKey: ['cycles'] })
      setMutError(null)
    },
    onError: (e) => setMutError(getErrorMessage(e)),
  })

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={3}>Allocation Console</Typography>

      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {STEPS.map((label) => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
      </Stepper>

      {mutError && <Alert severity="error" sx={{ mb: 2 }}>{mutError}</Alert>}

      {activeStep === 0 && (
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" mb={2}>Cycles Ready for Allocation</Typography>
            {readyCycles.length === 0 && (
              <Alert severity="info">No cycles with status APPLICATIONS_CLOSED found.</Alert>
            )}
            {readyCycles.map((c) => (
              <Box
                key={c._id}
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                p={1.5}
                border="1px solid"
                borderColor="divider"
                borderRadius={1}
                mb={1}
              >
                <Typography fontWeight={600}>{c.name}</Typography>
                <Button
                  variant={selectedCycle?._id === c._id ? 'contained' : 'outlined'}
                  size="small"
                  onClick={() => setSelectedCycle(c)}
                >
                  {selectedCycle?._id === c._id ? 'Selected' : 'Select'}
                </Button>
              </Box>
            ))}
            <Box mt={2}>
              <Button
                variant="contained"
                disabled={!selectedCycle || previewMut.isPending}
                onClick={() => previewMut.mutate()}
              >
                {previewMut.isPending ? 'Loading preview…' : 'Preview Allocation'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {activeStep >= 1 && preview && (
        <Card elevation={2} sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" mb={2}>Preview — {selectedCycle?.name}</Typography>
            <Table size="small" component={Paper} variant="outlined">
              <TableBody>
                {Object.entries(preview).map(([k, v]) => (
                  <TableRow key={k}>
                    <TableCell sx={{ fontWeight: 600 }}>{k.replace(/_/g, ' ')}</TableCell>
                    <TableCell sx={{ fontFamily: k.includes('seed') ? 'monospace' : 'inherit' }}>{String(v)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {activeStep === 1 && (
              <Box mt={2}>
                <Button variant="contained" color="warning" onClick={() => setConfirmRun(true)}>
                  Run Allocation
                </Button>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {activeStep >= 2 && runResult && (
        <Card elevation={2} sx={{ mb: 2 }}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <Typography variant="h6">Allocation Complete</Typography>
              <Chip label="ALLOTMENT_ACTIVE" color="success" size="small" />
            </Box>
            <Table size="small" component={Paper} variant="outlined">
              <TableBody>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Allotted / Waitlisted</TableCell>
                  <TableCell>{runResult.allotted} allotted · {runResult.waitlisted} waitlisted</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Seed Commitment</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>{runResult.seed_commitment}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Seed Revealed</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>{runResult.seed_revealed}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Input Hash</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>{runResult.input_hash}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Output Hash</TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>{runResult.output_hash}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <Box mt={2}>
              <Button variant="outlined" onClick={() => cascadeMut.mutate()} disabled={cascadeMut.isPending}>
                {cascadeMut.isPending ? 'Running Cascade…' : 'Run Cascade (for freed slots)'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {activeStep >= 3 && cascadeResult && (
        <Alert severity="success">
          Cascade Round #{cascadeResult.round_no}: allotted {cascadeResult.allotted ?? 0} · remaining waitlisted {cascadeResult.remaining_waitlisted ?? 0}.
        </Alert>
      )}

      <ConfirmDialog
        open={confirmRun}
        title="Run Allocation"
        message={`This will execute Round-1 allocation for cycle "${selectedCycle?.name}". Rooms will be HELD pending member acceptance (no payment step). Continue?`}
        onConfirm={() => { setConfirmRun(false); runMut.mutate() }}
        onCancel={() => setConfirmRun(false)}
      />
    </Box>
  )
}

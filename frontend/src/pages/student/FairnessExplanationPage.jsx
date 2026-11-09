import React, { useState } from 'react'
import {
  Box, Typography, Card, CardContent, Accordion, AccordionSummary, AccordionDetails,
  Grid, Chip, Table, TableHead, TableBody, TableRow, TableCell, TableContainer,
  Paper, MenuItem, TextField, Alert,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { useQuery } from '@tanstack/react-query'
import { getFairnessExplanation } from '../../api/auth'
import { listCycles } from '../../api/cycle'
import LoadingSpinner from '../../components/common/LoadingSpinner'

const FAQ = [
  {
    q: 'How are fairness credits used?',
    a: 'Your application weight is 1 + credits (for groups, the group policy such as MEAN of member credits). Higher weight gives higher probability of earlier placement in Efraimidis-Spirakis Weighted Random Serial Dictatorship.',
  },
  {
    q: 'What are Priority Tiers?',
    a: 'Students with verified accessibility accommodations receive Tier 0 placement before standard Tier 1 applications.',
  },
  {
    q: 'How is a room confirmed?',
    a: 'There is no payment step. When offered a HELD room, every group member clicks Accept before the hold expires to confirm the room.',
  },
  {
    q: 'What happens at cycle settlement?',
    a: 'Rank #1: -3, #2: -2, #3: -1, #4–5: 0, #6+/fallback: +1; Unallotted: +2; Declined/Expired (forfeit): -2; Late Cancel: -1; Admin Revoked: 0 (clamped to [0, 10]).',
  },
  {
    q: 'What is cascade allocation?',
    a: 'Freed rooms from declined or expired offers are assigned strictly in the original Round-1 weighted random order without re-rolling randomness.',
  },
]

export default function FairnessExplanationPage() {
  const [cycleId, setCycleId] = useState('')
  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const { data: explanation, isLoading } = useQuery({
    queryKey: ['my-fairness', cycleId],
    queryFn: () => getFairnessExplanation(cycleId || undefined),
  })

  if (isLoading) return <LoadingSpinner />

  const app = explanation?.application
  const allot = explanation?.allotment

  return (
    <Box sx={{ p: 3, maxWidth: 960 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Box>
          <Typography variant="h4" fontWeight={700}>My Fairness Explanation</Typography>
          <Typography color="text.secondary">
            Transparent breakdown of your lottery weight, draw order, and choice evaluation.
          </Typography>
        </Box>
        {cycles?.length > 0 && (
          <TextField
            select
            label="Cycle"
            size="small"
            value={cycleId}
            onChange={(e) => setCycleId(e.target.value)}
            sx={{ minWidth: 240 }}
          >
            <MenuItem value="">Most recent cycle</MenuItem>
            {cycles.map((c) => (
              <MenuItem key={c._id} value={c._id}>{c.name}</MenuItem>
            ))}
          </TextField>
        )}
      </Box>

      <Grid container spacing={2} mb={3}>
        <Grid item xs={6} sm={3}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">My Credits</Typography>
              <Typography variant="h4" fontWeight={700} color="primary.main">
                {explanation?.credits ?? '—'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">Group Weight</Typography>
              <Typography variant="h4" fontWeight={700}>
                {app?.weight != null ? Number(app.weight).toFixed(2) : '—'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">Priority Tier</Typography>
              <Typography variant="h5" fontWeight={700}>
                {app ? (app.tier === 0 ? 'Tier 0 (Access.)' : 'Tier 1') : '—'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={3}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="overline" color="text.secondary">Draw Order</Typography>
              <Typography variant="h5" fontWeight={700}>
                {app?.order_index != null
                  ? `#${app.order_index + 1} / ${app.total_applicants}`
                  : 'Pending'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {app ? (
        <Card elevation={2} sx={{ mb: 3 }}>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2} flexWrap="wrap" gap={1}>
              <Typography variant="h6" fontWeight={600}>
                Choice Breakdown ({explanation?.cycle?.name})
              </Typography>
              <Box display="flex" gap={1}>
                <Chip label={`App: ${app.status}`} size="small" />
                {allot && (
                  <Chip
                    label={`Allotment: ${allot.status}${allot.room_no ? ` · Room ${allot.room_no}` : ''}`}
                    color={allot.status === 'CONFIRMED' ? 'success' : 'warning'}
                    size="small"
                  />
                )}
                {explanation?.expected_credit_delta != null && (
                  <Chip
                    label={`Settlement Δ: ${explanation.expected_credit_delta > 0 ? `+${explanation.expected_credit_delta}` : explanation.expected_credit_delta}`}
                    color={explanation.expected_credit_delta >= 0 ? 'info' : 'secondary'}
                    size="small"
                    variant="outlined"
                  />
                )}
              </Box>
            </Box>

            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell><strong>Rank</strong></TableCell>
                    <TableCell><strong>Preference</strong></TableCell>
                    <TableCell><strong>Type</strong></TableCell>
                    <TableCell><strong>Outcome</strong></TableCell>
                    <TableCell><strong>Explanation</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(explanation.choice_explanations || []).map((c) => (
                    <TableRow key={c.rank}>
                      <TableCell>#{c.rank}</TableCell>
                      <TableCell>{c.target}</TableCell>
                      <TableCell>{c.kind}</TableCell>
                      <TableCell>
                        <Chip
                          label={c.status}
                          size="small"
                          color={c.status === 'MATCHED' ? 'success' : 'default'}
                        />
                      </TableCell>
                      <TableCell>{c.reason}</TableCell>
                    </TableRow>
                  ))}
                  {(!explanation.choice_explanations || explanation.choice_explanations.length === 0) && (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ color: 'text.secondary' }}>
                        No ranked choices recorded.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      ) : (
        <Alert severity="info" sx={{ mb: 3 }}>
          No application submitted for this cycle yet.
        </Alert>
      )}

      <Typography variant="h6" fontWeight={600} mb={2}>Frequently Asked Questions</Typography>
      {FAQ.map((item, i) => (
        <Accordion key={i} elevation={1} sx={{ mb: 1 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography fontWeight={600}>{item.q}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography color="text.secondary">{item.a}</Typography>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  )
}

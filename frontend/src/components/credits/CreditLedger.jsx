import React from 'react'
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableContainer,
  Paper,
  Typography,
  Chip,
} from '@mui/material'
import { formatDatetime } from '../../utils/dates'

/**
 * Table of credit ledger entries.
 */
export default function CreditLedger({ entries = [] }) {
  if (entries.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
        No credit history yet.
      </Typography>
    )
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell><strong>Date</strong></TableCell>
            <TableCell><strong>Event</strong></TableCell>
            <TableCell align="right"><strong>Change</strong></TableCell>
            <TableCell align="right"><strong>Credits After</strong></TableCell>
            <TableCell><strong>Reason</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {entries.map((entry, i) => {
            const delta = entry.delta ?? entry.amount ?? 0
            const deltaColor =
              delta > 0 ? 'success.main' : delta < 0 ? 'error.main' : 'text.secondary'
            const afterVal = entry.credits_after ?? entry.balance_after
            return (
              <TableRow key={entry._id ?? entry.id ?? i} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {formatDatetime(entry.created_at ?? entry.date)}
                </TableCell>
                <TableCell>
                  <Chip
                    label={entry.event_type ?? entry.type ?? '—'}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.7rem' }}
                  />
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" fontWeight={600} color={deltaColor}>
                    {delta > 0 ? `+${delta}` : delta}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {afterVal ?? '—'}
                  </Typography>
                </TableCell>
                <TableCell sx={{ maxWidth: 260, wordBreak: 'break-word' }}>
                  <Typography variant="caption" color="text.secondary">
                    {entry.reason || entry.note || entry.description || '—'}
                  </Typography>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

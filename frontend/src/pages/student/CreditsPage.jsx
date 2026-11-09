import React from 'react'
import { Box, Typography, Card, CardContent } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { getCredits } from '../../api/auth'
import CreditLedger from '../../components/credits/CreditLedger'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'

export default function CreditsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['my-credits'],
    queryFn: () => getCredits(),
  })

  if (isLoading) return <LoadingSpinner />
  if (error) return <Box sx={{ p: 3 }}><ErrorAlert error={error} /></Box>

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" fontWeight={700} mb={3}>My Credits</Typography>

      <Card elevation={2} sx={{ mb: 3, maxWidth: 260 }}>
        <CardContent>
          <Typography variant="overline" color="text.secondary">Current Balance</Typography>
          <Typography variant="h3" fontWeight={700} color="primary.main">
            {data?.credits ?? '—'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            fairness credits (bounds: 0 – 10)
          </Typography>
        </CardContent>
      </Card>

      <Typography variant="h6" mb={2}>Credit History</Typography>
      <CreditLedger entries={data?.ledger || []} />
    </Box>
  )
}

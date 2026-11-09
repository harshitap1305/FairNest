import React, { useState } from 'react'
import {
  Box, Typography, Card, CardContent, Grid, MenuItem, TextField, Alert,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { listCycles } from '../../api/cycle'
import { getFairnessReport } from '../../api/admin'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ErrorAlert from '../../components/common/ErrorAlert'

export default function FairnessDashboardPage() {
  const [cycleId, setCycleId] = useState('')
  const { data: cycles } = useQuery({ queryKey: ['cycles'], queryFn: () => listCycles() })
  const { data: report, isLoading, error } = useQuery({
    queryKey: ['fairness-report', cycleId],
    queryFn: () => getFairnessReport(cycleId ? { cycle_id: cycleId } : {}),
  })

  const bandData = (report?.success_by_band || []).map((b) => ({
    band: b.band,
    rate: Number(((b.success_rate || 0) * 100).toFixed(1)),
  }))

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={3}>
        <Typography variant="h4" fontWeight={700}>Fairness Dashboard</Typography>
        <TextField
          select
          label="Scope"
          value={cycleId}
          onChange={(e) => setCycleId(e.target.value)}
          sx={{ minWidth: 280 }}
          size="small"
        >
          <MenuItem value="">All Visible Cycles</MenuItem>
          {(cycles || []).map((c) => (
            <MenuItem key={c._id} value={c._id}>{c.name}</MenuItem>
          ))}
        </TextField>
      </Box>

      {error && <ErrorAlert error={error} />}
      {isLoading && <LoadingSpinner />}

      {report && (
        <>
          {/* KPI Summary */}
          <Grid container spacing={2} mb={3}>
            {[
              { label: 'Total Applications', value: report.total_applications ?? 0 },
              { label: 'Confirmed', value: report.confirmed ?? 0 },
              { label: 'Success Rate', value: `${((report.success_rate || 0) * 100).toFixed(1)}%` },
              { label: "Jain's Index", value: (report.jain_index ?? 1).toFixed(4) },
              { label: 'Top-1 Rate', value: `${((report.top_1_rate || 0) * 100).toFixed(1)}%` },
              { label: 'Avg Rank', value: report.average_rank ? report.average_rank.toFixed(2) : '—' },
            ].map((kpi) => (
              <Grid item xs={6} sm={4} md={2} key={kpi.label}>
                <Card elevation={2}>
                  <CardContent>
                    <Typography variant="caption" color="text.secondary">{kpi.label}</Typography>
                    <Typography variant="h5" fontWeight={700}>{kpi.value}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" mb={2}>Success Rate by Credit Band</Typography>
                  {bandData.length === 0 ? (
                    <Alert severity="info">No credit-band data yet.</Alert>
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={bandData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="band" />
                        <YAxis tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                        <Tooltip formatter={(v) => `${v}%`} />
                        <Bar dataKey="rate" fill="#1565C0" name="Success %" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" mb={2}>Rank Obtained Distribution</Typography>
                  {!report.rank_distribution?.length ? (
                    <Alert severity="info">No confirmed rank distribution yet.</Alert>
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={report.rank_distribution}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="rank" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#2E7D32" name="Allotments" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" mb={2}>Group Size Demand vs Room Supply</Typography>
                  {!report.demand_vs_supply?.length ? (
                    <Alert severity="info">No demand/supply data yet.</Alert>
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={report.demand_vs_supply}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="size" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="demand" fill="#E65100" name="Applications" />
                        <Bar dataKey="supply" fill="#1565C0" name="Rooms" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardContent>
                  <Typography variant="h6" mb={2}>Credit Balance Distribution</Typography>
                  {!report.credit_distribution?.length ? (
                    <Alert severity="info">No credit accounts yet.</Alert>
                  ) : (
                    <ResponsiveContainer width="100%" height={260}>
                      <BarChart data={report.credit_distribution}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="credits" />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#6A1B9A" name="Students" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </>
      )}
    </Box>
  )
}

import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  Box,
  Typography,
} from '@mui/material'
import DashboardIcon from '@mui/icons-material/Dashboard'
import GroupIcon from '@mui/icons-material/Group'
import TuneIcon from '@mui/icons-material/Tune'
import HotelIcon from '@mui/icons-material/Hotel'
import StarIcon from '@mui/icons-material/Star'
import BalanceIcon from '@mui/icons-material/Balance'
import NotificationsIcon from '@mui/icons-material/Notifications'
import PeopleIcon from '@mui/icons-material/People'
import CycleIcon from '@mui/icons-material/Autorenew'
import ScheduleIcon from '@mui/icons-material/Schedule'
import AllocationIcon from '@mui/icons-material/AccountTree'
import CascadeIcon from '@mui/icons-material/LowPriority'
import BarChartIcon from '@mui/icons-material/BarChart'
import HistoryIcon from '@mui/icons-material/History'
import MeetingRoomIcon from '@mui/icons-material/MeetingRoom'
import AccessibleIcon from '@mui/icons-material/Accessible'
import MonitorIcon from '@mui/icons-material/Monitor'
import OccupancyIcon from '@mui/icons-material/Apartment'
import VerifiedIcon from '@mui/icons-material/VerifiedUser'
import AdminPanelIcon from '@mui/icons-material/AdminPanelSettings'
import SpaceDashboardIcon from '@mui/icons-material/SpaceDashboard'
import { useAuth } from '../../auth/AuthContext'

const NAV = {
  STUDENT: [
    { label: 'Dashboard', icon: <DashboardIcon />, path: '/student', exact: true },
    { label: 'My Group', icon: <GroupIcon />, path: '/student/group' },
    { label: 'Preferences', icon: <TuneIcon />, path: '/student/preferences' },
    { label: 'My Allotment', icon: <HotelIcon />, path: '/student/allotment' },
    { label: 'Credits', icon: <StarIcon />, path: '/student/credits' },
    { label: 'How Fairness Works', icon: <BalanceIcon />, path: '/student/fairness' },
    { label: 'Notifications', icon: <NotificationsIcon />, path: '/notifications' },
  ],
  WARDEN: [
    { label: 'Overview', icon: <SpaceDashboardIcon />, path: '/warden/overview' },
    { label: 'Rooms', icon: <MeetingRoomIcon />, path: '/warden/rooms' },
    { label: 'Accessibility Queue', icon: <AccessibleIcon />, path: '/warden/accessibility' },
    { label: 'Allotment Monitor', icon: <MonitorIcon />, path: '/warden/allotments' },
    { label: 'Occupancy', icon: <OccupancyIcon />, path: '/warden/occupancy' },
    { label: 'Notifications', icon: <NotificationsIcon />, path: '/notifications' },
  ],
  ADMIN: [
    { label: 'Overview', icon: <SpaceDashboardIcon />, path: '/admin/overview' },
    { label: 'Cycles', icon: <CycleIcon />, path: '/admin/cycles' },
    { label: 'Release Scheduler', icon: <ScheduleIcon />, path: '/admin/scheduler' },
    { label: 'Allocation Console', icon: <AllocationIcon />, path: '/admin/allocation' },
    { label: 'Cascade', icon: <CascadeIcon />, path: '/admin/cascade' },
    { label: 'Users', icon: <PeopleIcon />, path: '/admin/users' },
    { label: 'Rooms', icon: <MeetingRoomIcon />, path: '/warden/rooms' },
    { label: 'Accessibility', icon: <AccessibleIcon />, path: '/warden/accessibility' },
    { label: 'Allotment Monitor', icon: <MonitorIcon />, path: '/warden/allotments' },
    { label: 'Occupancy', icon: <OccupancyIcon />, path: '/warden/occupancy' },
    { label: 'Fairness Dashboard', icon: <BarChartIcon />, path: '/admin/fairness' },
    { label: 'Verify Allocation', icon: <VerifiedIcon />, path: '/auditor/verify' },
    { label: 'Audit Log', icon: <HistoryIcon />, path: '/admin/audit' },
    { label: 'Notifications', icon: <NotificationsIcon />, path: '/notifications' },
  ],
  AUDITOR: [
    { label: 'Verify Allocation', icon: <VerifiedIcon />, path: '/auditor/verify' },
    { label: 'Fairness Dashboard', icon: <BarChartIcon />, path: '/auditor/fairness' },
    { label: 'Audit Log', icon: <HistoryIcon />, path: '/auditor/audit' },
    { label: 'Notifications', icon: <NotificationsIcon />, path: '/notifications' },
  ],
  SUPER_ADMIN: [
    { label: 'Roles & Access', icon: <AdminPanelIcon />, path: '/superadmin/roles' },
    { label: 'Users', icon: <PeopleIcon />, path: '/superadmin/users' },
    { label: 'Overview', icon: <SpaceDashboardIcon />, path: '/admin/overview' },
    { label: 'Cycles', icon: <CycleIcon />, path: '/admin/cycles' },
    { label: 'Release Scheduler', icon: <ScheduleIcon />, path: '/admin/scheduler' },
    { label: 'Allocation Console', icon: <AllocationIcon />, path: '/admin/allocation' },
    { label: 'Cascade', icon: <CascadeIcon />, path: '/admin/cascade' },
    { label: 'Rooms', icon: <MeetingRoomIcon />, path: '/warden/rooms' },
    { label: 'Accessibility', icon: <AccessibleIcon />, path: '/warden/accessibility' },
    { label: 'Allotment Monitor', icon: <MonitorIcon />, path: '/warden/allotments' },
    { label: 'Occupancy', icon: <OccupancyIcon />, path: '/warden/occupancy' },
    { label: 'Fairness Dashboard', icon: <BarChartIcon />, path: '/admin/fairness' },
    { label: 'Verify Allocation', icon: <VerifiedIcon />, path: '/auditor/verify' },
    { label: 'Audit Log', icon: <HistoryIcon />, path: '/admin/audit' },
    { label: 'Notifications', icon: <NotificationsIcon />, path: '/notifications' },
  ],
}

export default function Sidebar() {
  const { role } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const items = NAV[role] ?? []

  return (
    <Box sx={{ overflow: 'auto' }}>
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase">
          {role?.replace('_', ' ') ?? 'Menu'}
        </Typography>
      </Box>
      <Divider />
      <List dense>
        {items.map(({ label, icon, path, exact }) => {
          const isActive = exact
            ? location.pathname === path
            : location.pathname === path || location.pathname.startsWith(`${path}/`)
          return (
            <ListItemButton
              key={path}
              selected={isActive}
              onClick={() => navigate(path)}
              sx={{
                borderRadius: 1,
                mx: 0.5,
                mb: 0.25,
                '&.Mui-selected': {
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                  '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                  '&:hover': { bgcolor: 'primary.dark' },
                },
              }}
            >
              <ListItemIcon sx={{ minWidth: 36 }}>{icon}</ListItemIcon>
              <ListItemText primary={label} primaryTypographyProps={{ fontSize: 13.5 }} />
            </ListItemButton>
          )
        })}
      </List>
    </Box>
  )
}

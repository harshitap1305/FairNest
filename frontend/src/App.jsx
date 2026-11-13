import React, { Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import RoleRoute from './auth/RoleRoute'
import LoadingSpinner from './components/common/LoadingSpinner'
import AppShell from './components/layout/AppShell'

// Public pages
import LoginPage from './pages/public/LoginPage'
import ActivatePage from './pages/public/ActivatePage'
import ForgotPasswordPage from './pages/public/ForgotPasswordPage'
import ResetPasswordPage from './pages/public/ResetPasswordPage'

// Student pages
import StudentDashboard from './pages/student/Dashboard'
import MyGroupPage from './pages/student/MyGroupPage'
import PreferencesPage from './pages/student/PreferencesPage'
import MyAllotmentPage from './pages/student/MyAllotmentPage'
import CreditsPage from './pages/student/CreditsPage'
import FairnessExplanationPage from './pages/student/FairnessExplanationPage'
import NotificationsPage from './pages/student/NotificationsPage'

// Admin pages
import UsersPage from './pages/admin/UsersPage'
import CycleListPage from './pages/admin/CycleListPage'
import CycleEditorPage from './pages/admin/CycleEditorPage'
import ReleaseSchedulerPage from './pages/admin/ReleaseSchedulerPage'
import AllocationConsolePage from './pages/admin/AllocationConsolePage'
import CascadePage from './pages/admin/CascadePage'
import FairnessDashboardPage from './pages/admin/FairnessDashboardPage'
import AuditLogPage from './pages/admin/AuditLogPage'

// Warden pages
import RoomsPage from './pages/warden/RoomsPage'
import AccessibilityQueuePage from './pages/warden/AccessibilityQueuePage'
import AllotmentMonitorPage from './pages/warden/AllotmentMonitorPage'
import OccupancyPage from './pages/warden/OccupancyPage'

// Auditor pages
import VerifyAllocationPage from './pages/auditor/VerifyAllocationPage'

// SuperAdmin pages
import RolesAndAccessPage from './pages/superadmin/RolesAndAccessPage'

// Shared pages
import AccountPage from './pages/account/AccountPage'

const ALL_ROLES = ['STUDENT', 'WARDEN', 'ADMIN', 'AUDITOR', 'SUPER_ADMIN']

function RoleHome() {
  const { role, loading, isAuthenticated } = useAuth()
  if (loading) return <LoadingSpinner />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (role === 'STUDENT') return <Navigate to="/student" replace />
  if (role === 'ADMIN') return <Navigate to="/admin" replace />
  if (role === 'WARDEN') return <Navigate to="/warden" replace />
  if (role === 'AUDITOR') return <Navigate to="/auditor" replace />
  if (role === 'SUPER_ADMIN') return <Navigate to="/superadmin" replace />
  return <Navigate to="/login" replace />
}

function ProtectedLayout({ roles }) {
  return (
    <RoleRoute roles={roles}>
      <AppShell />
    </RoleRoute>
  )
}

export default function App() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        {/* ── Public (no shell) ── */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/activate" element={<ActivatePage />} />
        <Route path="/forgot" element={<ForgotPasswordPage />} />
        <Route path="/reset" element={<ResetPasswordPage />} />

        {/* ── Root → role home ── */}
        <Route path="/" element={<RoleHome />} />

        {/* ── Shared authenticated notifications ── */}
        <Route element={<ProtectedLayout roles={ALL_ROLES} />}>
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>

        {/* ── Student ── */}
        <Route element={<ProtectedLayout roles={['STUDENT']} />}>
          <Route path="/student" element={<StudentDashboard />} />
          <Route path="/student/group" element={<MyGroupPage />} />
          <Route path="/student/preferences" element={<PreferencesPage />} />
          <Route path="/student/allotment" element={<MyAllotmentPage />} />
          <Route path="/student/credits" element={<CreditsPage />} />
          <Route path="/student/fairness" element={<FairnessExplanationPage />} />
          <Route path="/student/notifications" element={<NotificationsPage />} />
        </Route>

        {/* ── Admin ── */}
        <Route element={<ProtectedLayout roles={['ADMIN', 'SUPER_ADMIN']} />}>
          <Route path="/admin" element={<CycleListPage />} />
          <Route path="/admin/users" element={<UsersPage />} />
          <Route path="/admin/cycles" element={<CycleListPage />} />
          <Route path="/admin/cycles/new" element={<CycleEditorPage />} />
          <Route path="/admin/cycles/:cycleId" element={<CycleEditorPage />} />
          <Route path="/admin/scheduler" element={<ReleaseSchedulerPage />} />
          <Route path="/admin/allocation" element={<AllocationConsolePage />} />
          <Route path="/admin/cascade" element={<CascadePage />} />
          <Route path="/admin/fairness" element={<FairnessDashboardPage />} />
          <Route path="/admin/audit" element={<AuditLogPage />} />
        </Route>

        {/* ── Warden ── */}
        <Route element={<ProtectedLayout roles={['WARDEN', 'ADMIN', 'SUPER_ADMIN']} />}>
          <Route path="/warden" element={<RoomsPage />} />
          <Route path="/warden/rooms" element={<RoomsPage />} />
          <Route path="/warden/accessibility" element={<AccessibilityQueuePage />} />
          <Route path="/warden/allotments" element={<AllotmentMonitorPage />} />
          <Route path="/warden/occupancy" element={<OccupancyPage />} />
        </Route>

        {/* ── Auditor ── */}
        <Route element={<ProtectedLayout roles={['AUDITOR', 'ADMIN', 'SUPER_ADMIN']} />}>
          <Route path="/auditor" element={<VerifyAllocationPage />} />
          <Route path="/auditor/verify" element={<VerifyAllocationPage />} />
          <Route path="/auditor/fairness" element={<FairnessDashboardPage />} />
          <Route path="/auditor/audit" element={<AuditLogPage />} />
        </Route>

        {/* ── SuperAdmin ── */}
        <Route element={<ProtectedLayout roles={['SUPER_ADMIN']} />}>
          <Route path="/superadmin" element={<RolesAndAccessPage />} />
          <Route path="/superadmin/roles" element={<RolesAndAccessPage />} />
          <Route path="/superadmin/users" element={<UsersPage />} />
        </Route>

        {/* ── Catch-all ── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}

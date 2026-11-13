import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import RoleRoute from './auth/RoleRoute'
import LoadingSpinner from './components/common/LoadingSpinner'
import AppShell from './components/layout/AppShell'

// Public pages
import LoginPage from './pages/public/LoginPage'
const ActivatePage = lazy(() => import('./pages/public/ActivatePage'))
const ForgotPasswordPage = lazy(() => import('./pages/public/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('./pages/public/ResetPasswordPage'))

// Student pages
const StudentDashboard = lazy(() => import('./pages/student/Dashboard'))
const MyGroupPage = lazy(() => import('./pages/student/MyGroupPage'))
const PreferencesPage = lazy(() => import('./pages/student/PreferencesPage'))
const MyAllotmentPage = lazy(() => import('./pages/student/MyAllotmentPage'))
const CreditsPage = lazy(() => import('./pages/student/CreditsPage'))
const FairnessExplanationPage = lazy(() => import('./pages/student/FairnessExplanationPage'))
const NotificationsPage = lazy(() => import('./pages/student/NotificationsPage'))

// Admin pages
const UsersPage = lazy(() => import('./pages/admin/UsersPage'))
const CycleListPage = lazy(() => import('./pages/admin/CycleListPage'))
const CycleEditorPage = lazy(() => import('./pages/admin/CycleEditorPage'))
const ReleaseSchedulerPage = lazy(() => import('./pages/admin/ReleaseSchedulerPage'))
const AllocationConsolePage = lazy(() => import('./pages/admin/AllocationConsolePage'))
const CascadePage = lazy(() => import('./pages/admin/CascadePage'))
const FairnessDashboardPage = lazy(() => import('./pages/admin/FairnessDashboardPage'))
const AuditLogPage = lazy(() => import('./pages/admin/AuditLogPage'))
const OverviewPage = lazy(() => import('./pages/admin/OverviewPage'))

// Warden pages
const RoomsPage = lazy(() => import('./pages/warden/RoomsPage'))
const AccessibilityQueuePage = lazy(() => import('./pages/warden/AccessibilityQueuePage'))
const AllotmentMonitorPage = lazy(() => import('./pages/warden/AllotmentMonitorPage'))
const OccupancyPage = lazy(() => import('./pages/warden/OccupancyPage'))

// Auditor pages
const VerifyAllocationPage = lazy(() => import('./pages/auditor/VerifyAllocationPage'))

// SuperAdmin pages
const RolesAndAccessPage = lazy(() => import('./pages/superadmin/RolesAndAccessPage'))

// Shared pages
const AccountPage = lazy(() => import('./pages/account/AccountPage'))

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
          <Route path="/admin" element={<OverviewPage />} />
          <Route path="/admin/overview" element={<OverviewPage />} />
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
          <Route path="/warden/overview" element={<OverviewPage />} />
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

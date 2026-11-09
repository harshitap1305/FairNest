import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import LoadingSpinner from '../components/common/LoadingSpinner'

/**
 * RoleRoute – guards a route so that:
 *   - Unauthenticated users are redirected to /login
 *   - Authenticated users with the wrong role are redirected to /
 *
 * @param {string[]} roles  Allowed role strings (e.g. ['STUDENT', 'ADMIN'])
 * @param {ReactNode} children
 */
export default function RoleRoute({ roles, children }) {
  const { isAuthenticated, role, loading } = useAuth()
  const location = useLocation()

  if (loading) return <LoadingSpinner />

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (roles && roles.length > 0 && !roles.includes(role)) {
    return <Navigate to="/" replace />
  }

  return children
}

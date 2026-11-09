import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { login as apiLogin, logout as apiLogout, refreshSession, getMe } from '../api/auth'
import { setToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [accessToken, setAccessToken] = useState(null)
  const [loading, setLoading] = useState(true)

  const storeToken = useCallback((token) => {
    setToken(token)
    setAccessToken(token)
  }, [])

  const clearSession = useCallback(() => {
    setToken(null)
    setAccessToken(null)
    setUser(null)
  }, [])

  const silentRefresh = useCallback(async () => {
    try {
      const data = await refreshSession()
      const token = data?.access_token
      if (token) {
        storeToken(token)
        const me = await getMe()
        setUser(me)
      } else {
        clearSession()
      }
    } catch {
      clearSession()
    } finally {
      setLoading(false)
    }
  }, [storeToken, clearSession])

  useEffect(() => {
    silentRefresh()
    const handleForceLogout = () => clearSession()
    window.addEventListener('auth:logout', handleForceLogout)
    return () => window.removeEventListener('auth:logout', handleForceLogout)
  }, [silentRefresh, clearSession])

  const login = useCallback(async (identifier, password) => {
    const res = await apiLogin(identifier, password)
    const token = res?.access_token
    if (token) {
      storeToken(token)
      const me = await getMe()
      setUser(me)
      return me
    }
    return res
  }, [storeToken])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // best-effort
    } finally {
      clearSession()
    }
  }, [clearSession])

  const refreshUser = useCallback(async () => {
    const me = await getMe()
    setUser(me)
    return me
  }, [])

  const isAuthenticated = Boolean(accessToken && user)
  const role = user?.role ?? null

  const value = {
    user,
    accessToken,
    isAuthenticated,
    role,
    loading,
    login,
    logout,
    silentRefresh,
    refreshUser,
    setUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

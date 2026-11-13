import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { ThemeProvider, CssBaseline, useMediaQuery } from '@mui/material'
import { buildTheme } from './theme'

const STORAGE_KEY = 'fairnest.colorMode'
const ColorModeContext = createContext({ mode: 'light', toggle: () => {} })

function readStoredMode() {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

/** Light/dark theme provider that remembers the choice and follows the OS by default. */
export function ColorModeProvider({ children }) {
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  const [stored, setStored] = useState(readStoredMode)
  const mode = stored ?? (prefersDark ? 'dark' : 'light')

  useEffect(() => {
    if (!stored) return
    try {
      window.localStorage.setItem(STORAGE_KEY, stored)
    } catch {
      // storage unavailable (private mode etc.) - keep the in-memory choice
    }
  }, [stored])

  const value = useMemo(
    () => ({ mode, toggle: () => setStored(mode === 'dark' ? 'light' : 'dark') }),
    [mode]
  )
  const theme = useMemo(() => buildTheme(mode), [mode])

  return (
    <ColorModeContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  )
}

export const useColorMode = () => useContext(ColorModeContext)

import { createTheme } from '@mui/material/styles'

/** Build the FairNest theme for 'light' or 'dark' mode. */
export function buildTheme(mode = 'light') {
  const dark = mode === 'dark'
  return createTheme({
    palette: {
      mode,
      primary: {
        main: dark ? '#64a1f4' : '#1565C0',
        light: '#5e92f3',
        dark: '#003c8f',
        contrastText: dark ? '#0b1726' : '#ffffff',
      },
      secondary: {
        main: dark ? '#ff9e5e' : '#E65100',
        light: '#ff833a',
        dark: '#ac1900',
        contrastText: '#ffffff',
      },
      background: dark
        ? { default: '#0f141a', paper: '#171e26' }
        : { default: '#f4f6f9', paper: '#ffffff' },
      success: { main: dark ? '#66bb6a' : '#2e7d32' },
      warning: { main: dark ? '#ffa726' : '#ed6c02' },
      error: { main: dark ? '#f44336' : '#d32f2f' },
    },
    typography: {
      fontFamily: 'Roboto, Arial, sans-serif',
      h4: { fontWeight: 700 },
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 },
    },
    shape: { borderRadius: 8 },
    components: {
      MuiButton: {
        styleOverrides: {
          root: { textTransform: 'none', fontWeight: 500 },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: { boxShadow: dark ? '0 2px 8px rgba(0,0,0,0.5)' : '0 2px 8px rgba(0,0,0,0.08)' },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { fontWeight: 500 },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: dark ? { backgroundImage: 'none', backgroundColor: '#12355e' } : {},
        },
      },
    },
  })
}

const theme = buildTheme('light')
export default theme

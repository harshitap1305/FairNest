import { createTheme } from '@mui/material/styles'

/** Build the FairNest theme for 'light' or 'dark' mode. */
export function buildTheme(mode = 'light') {
  const dark = mode === 'dark'
  return createTheme({
    palette: {
      mode,
      primary: {
        main: dark ? '#9e7cd8' : '#4C2A85',
        light: dark ? '#b99ee6' : '#7b5ab5',
        dark: dark ? '#6e47b0' : '#331a5e',
        contrastText: dark ? '#140b24' : '#ffffff',
      },
      secondary: {
        main: dark ? '#ff9e5e' : '#E65100',
        light: '#ff833a',
        dark: '#ac1900',
        contrastText: '#ffffff',
      },
      info: {
        main: dark ? '#b39ddb' : '#4C2A85',
        light: '#7b5ab5',
        dark: '#331a5e',
        contrastText: dark ? '#140b24' : '#ffffff',
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
          root: dark ? { backgroundImage: 'none', backgroundColor: '#331a5e' } : {},
        },
      },
    },
  })
}

const theme = buildTheme('light')
export default theme

import { createTheme } from '@mui/material/styles'

const theme = createTheme({
  palette: {
    primary: {
      main: '#1565C0',
      light: '#5e92f3',
      dark: '#003c8f',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#E65100',
      light: '#ff833a',
      dark: '#ac1900',
      contrastText: '#ffffff',
    },
    background: {
      default: '#f4f6f9',
      paper: '#ffffff',
    },
    success: { main: '#2e7d32' },
    warning: { main: '#ed6c02' },
    error: { main: '#d32f2f' },
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
        root: { boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500 },
      },
    },
  },
})

export default theme

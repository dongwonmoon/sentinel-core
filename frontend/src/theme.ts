// frontend/src/theme.ts
import { createTheme } from '@mui/material/styles';
import { red } from '@mui/material/colors';
import { Roboto } from 'next/font/google';

const roboto = Roboto({
  weight: ['300', '400', '500', '700'],
  subsets: ['latin'],
  display: 'swap',
});

// A custom theme for this application
const theme = createTheme({
  typography: {
    fontFamily: roboto.style.fontFamily,
  },
  palette: {
    primary: {
      main: '#556cd6', // A shade of indigo
    },
    secondary: {
      main: '#19857b', // A shade of teal
    },
    error: {
      main: red.A400,
    },
  },
});

export default theme;

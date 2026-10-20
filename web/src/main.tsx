import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { I18nProvider } from './i18n'
import { UserProvider } from './user'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <UserProvider>
        <App />
      </UserProvider>
    </I18nProvider>
  </StrictMode>,
)

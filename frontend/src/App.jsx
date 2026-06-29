import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Header from './components/layout/Header'
import SportView from './components/sports/SportView'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    }
  }
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Header />
      <SportView />
    </QueryClientProvider>
  )
}

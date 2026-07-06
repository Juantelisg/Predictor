import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Header from './components/layout/Header'
import SportView from './components/sports/SportView'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Render free tarda en despertar (spin-up 502/503) -> reintentar con backoff
      // exponential (~1+2+4+8s) para que la carga se auto-recupere en vez de quedar en error.
      retry: 4,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 15000),
      refetchOnWindowFocus: false,
    }
  }
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex flex-col h-screen overflow-hidden">
        <Header />
        <SportView />
      </div>
    </QueryClientProvider>
  )
}

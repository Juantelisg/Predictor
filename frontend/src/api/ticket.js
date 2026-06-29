import { api } from './client'

export const analyzeTicket = (body) => api.post('/api/ticket/analyze', body)
export const ticketLectura = (body) => api.post('/api/ticket/lectura', body)
export const getCartera    = (date) => api.get(`/api/cartera?date=${date}`)
export const getBudget     = ()     => api.get('/api/budget')

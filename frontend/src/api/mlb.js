import { api } from './client'

export const getMLBToday = (date) => api.get(`/api/mlb/today?date=${date}`)

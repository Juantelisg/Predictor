import { api } from './client'

export const getSoccerToday  = (date) => api.get(`/api/wc/today?date=${date}`)
export const getSoccerEdge   = (date) => api.get(`/api/edge/today?date=${date}`)
export const getSoccerHistory = (days = 14) => api.get(`/api/history?days=${days}`)
export const getTrackRecord  = (market) =>
  api.get(`/api/track-record${market ? `?market=${market}` : ''}`)

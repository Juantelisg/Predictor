import { create } from 'zustand'

// Global sport + sub-tab state
export const useSport = create((set) => ({
  sport: 'soccer',
  subtab: 'today',
  setSport: (sport) => set({ sport, subtab: 'today' }),
  setSubtab: (subtab) => set({ subtab }),
}))

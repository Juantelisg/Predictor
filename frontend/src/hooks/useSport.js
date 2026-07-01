import { create } from 'zustand'

export const useSport = create((set) => ({
  // Nivel 1: deporte activo
  sport: 'soccer',
  // Nivel 2: partido seleccionado (null = volver al picker)
  selectedMatch: null,
  // Nivel 3: estado dentro del workspace
  activeMainTab: 'team',      // 'team' | 'players'
  activeSubTeam: 'general',   // 'general' | 'home' | 'away'
  activeCategory: null,        // null = All, o el market key

  setSport: (sport) => set({
    sport,
    selectedMatch: null,
    activeMainTab: 'team',
    activeSubTeam: 'general',
    activeCategory: null,
  }),

  selectMatch: (match) => set({
    selectedMatch: match,
    activeMainTab: 'team',
    activeSubTeam: 'general',
    activeCategory: null,
  }),

  clearMatch: () => set({ selectedMatch: null }),

  setMainTab: (tab) => set({ activeMainTab: tab, activeSubTeam: 'general', activeCategory: null }),
  setSubTeam: (team) => set({ activeSubTeam: team, activeCategory: null }),
  setCategory: (cat) => set({ activeCategory: cat }),
}))

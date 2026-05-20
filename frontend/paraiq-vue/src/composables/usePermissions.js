// usePermissions.js
// Thin composable wrapper around the permissions Pinia store.
// Use this in components instead of importing the store directly.
//
// Usage:
//   const { can, isFirmAdmin, isScoped, role } = usePermissions()
//
//   Template:
//   <button v-if="can('documents', 'delete')">Delete</button>
//   <AdminPanel v-if="isFirmAdmin" />

import { usePermissionsStore } from '@/stores/permissions'
import { storeToRefs } from 'pinia'

export function usePermissions() {
  const store = usePermissionsStore()
  const { role, tier, loaded, isScoped, isFirmAdmin, isAttorney, isLegalStaff, gates } = storeToRefs(store)
  const { can, isTier, isRole } = store

  return {
    // Reactive state
    role, tier, loaded, isScoped,
    // Role group flags (computed refs - use directly in templates)
    isFirmAdmin, isAttorney, isLegalStaff,
    // Pre-built gates object (all 21 modules, reactive)
    gates,
    // Functions
    can, isTier, isRole,
  }
}

import {getAccountId} from './preferences'
export type DashboardPosition = {top:number; href:string; section:string; offset:number; kind:string; count:number}
export function dashboardReturnPosition():DashboardPosition | null {
  try {
    const value=JSON.parse(sessionStorage.getItem(`xyz_reading:${getAccountId()}:dashboard`) || 'null')
    return typeof value==='object' ? value : null
  } catch {return null}
}

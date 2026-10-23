export const API_URL = "http://192.168.0.12:8000";
export const REAL_USER_ID = "0df774fa-1a49-4744-a36c-07ff45f0bf4a";

export let CURRENT_USER_ID = REAL_USER_ID;

export function setCurrentUserId(id: string) {
  CURRENT_USER_ID = id;
}

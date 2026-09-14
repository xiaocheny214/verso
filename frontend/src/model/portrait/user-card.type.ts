import type { PortraitHorizon, Strength } from "./strength.type";

export interface Portrait {
  horizon: PortraitHorizon;
  strengths: Strength[];
}

export interface UserCard {
  id: string;
  name: string;
  avatar_url?: string | null;
  portraits: Portrait[];
}

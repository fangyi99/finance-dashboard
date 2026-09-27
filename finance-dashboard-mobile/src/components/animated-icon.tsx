import { useEffect } from "react";
import * as SplashScreen from "expo-splash-screen";

export function AnimatedSplashOverlay() {
  useEffect(() => {
    SplashScreen.hideAsync();
  }, []);

  return null;
}

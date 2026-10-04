import { useEffect } from "react";
import { useNavigate } from "react-router";

import { ProfilePicker } from "@/components/family/ProfilePicker";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useTvNavigation } from "@/tv/navigation";

interface ProfilesPageProps {
  tv?: boolean;
  /** Nobody signed in yet (the family device's start screen). */
  signedOut?: boolean;
  onPasswordLogin?: () => void;
}

/** "Wer schaut?" as its own screen – in the app, in the TV view and before signing in. */
export function ProfilesPage({ tv, signedOut, onPasswordLogin }: ProfilesPageProps) {
  useDocumentTitle("Wer schaut?");
  const navigate = useNavigate();
  const home = tv ? "/tv" : "/";
  const props = {
    tv,
    onDone: () => navigate(home, { replace: true }),
    onCancel: signedOut ? undefined : () => navigate(-1),
    onPasswordLogin,
  };
  return tv ? <TvProfiles {...props} /> : <ProfilePicker {...props} />;
}

function TvProfiles(props: React.ComponentProps<typeof ProfilePicker>) {
  useTvNavigation({ onBack: props.onCancel });
  // The remote needs something focused to start from: the first profile or PIN key.
  useEffect(() => {
    const focusFirst = () => {
      if (document.activeElement?.closest("[data-tv-focus]")) return;
      document
        .querySelector<HTMLElement>('[data-tv-key^="profile-"], [data-tv-key="pin-1"]')
        ?.focus();
    };
    const observer = new MutationObserver(focusFirst);
    observer.observe(document.body, { childList: true, subtree: true });
    focusFirst();
    return () => observer.disconnect();
  }, []);
  return <ProfilePicker {...props} />;
}

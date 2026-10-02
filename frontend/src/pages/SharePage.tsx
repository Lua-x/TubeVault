import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useOpenAddVideo } from "@/components/layout/addVideo";
import { PageSpinner } from "@/components/ui/Spinner";

const LINK = /https?:\/\/\S+/;

/** Target of the system share sheet (Android): opens "add video" with the shared link. */
export function SharePage() {
  const [params] = useSearchParams();
  const openAdd = useOpenAddVideo();
  const navigate = useNavigate();

  useEffect(() => {
    // Apps put the link in "url", "text" or even "title".
    const shared = ["url", "text", "title"].map((key) => params.get(key) ?? "").join(" ");
    openAdd(LINK.exec(shared)?.[0] ?? "");
    navigate("/", { replace: true });
  }, [params, openAdd, navigate]);

  return <PageSpinner />;
}

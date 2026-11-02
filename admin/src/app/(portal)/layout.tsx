import type { ReactNode } from "react";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { PanelFooter } from "@/components/shell/panel-footer";
import { ShortcutsHelp } from "@/components/shell/shortcuts-help";
import { Topbar } from "@/components/shell/topbar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { SessionProvider } from "@/hooks/use-session";
import { brandingCss, DEFAULT_BRANDING, getBranding } from "@/lib/branding";
import { getSession } from "@/lib/session";

export default async function PortalLayout({ children }: { children: ReactNode }) {
  const { me, navigation } = await getSession();
  const found = await getBranding(me.organization.slug);
  // An organization that has not set a display name still has its own name.
  const branding = {
    ...found,
    display_name: found.display_name === DEFAULT_BRANDING.display_name ? me.organization.name : found.display_name,
  };

  return (
    <SessionProvider value={{ me, navigation, branding }}>
      <style>{brandingCss(branding)}</style>
      <SidebarProvider>
        <AppSidebar />
        {/* min-w-0 all the way down: a wide table scrolls inside its own card, never the page. */}
        <SidebarInset className="min-w-0">
          <Topbar />
          <div
            id="content"
            tabIndex={-1}
            className="w-full min-w-0 flex-1 space-y-6 p-4 outline-none md:p-6"
          >
            {children}
          </div>
          <PanelFooter />
        </SidebarInset>
        <ShortcutsHelp />
      </SidebarProvider>
    </SessionProvider>
  );
}

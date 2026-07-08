import type { Metadata } from "next";
import Nav from "./Nav";
import Hero from "./Hero";
import MorningBrief from "./MorningBrief";
import ReceptionistDemo from "./ReceptionistDemo";
import Recovery from "./Recovery";
import Trust from "./Trust";
import Architecture from "./Architecture";
import CtaFooter from "./CtaFooter";

export const metadata: Metadata = {
  title: "Meridian — The clinic's best employee never clocks in",
  description:
    "Meridian is the clinic operating system: an AI receptionist and recovery companion that handles 90% of patient interactions and shows staff only the decisions that need a human.",
};

export default function MarketingHome() {
  return (
    <div className="mrd">
      <Nav />
      <main>
        <Hero />
        <MorningBrief />
        <ReceptionistDemo />
        <Recovery />
        <Trust />
        <Architecture />
        <CtaFooter />
      </main>
    </div>
  );
}

import { CharacterListClient } from "@/components/character-list/CharacterListClient";

export default function Home() {
  return (
    <main className="mx-auto flex h-dvh min-h-0 w-full max-w-[1600px] flex-col overflow-hidden px-4 py-4 pb-24 sm:px-6 md:py-8 lg:px-5 lg:pb-8">
      <CharacterListClient />
    </main>
  );
}

import { CharacterChatClient } from "@/components/character-chat/CharacterChatClient";
import { CharacterDetailSwitch } from "@/components/character-detail/CharacterDetailSwitch";

interface CharacterPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ from?: string }>;
}

export default async function CharacterPage({ params, searchParams }: CharacterPageProps) {
  const { id } = await params;
  const { from } = await searchParams;
  const fromArchive = from === "archive";

  if (fromArchive) {
    return <CharacterChatClient characterId={id} returnHref="/archive" returnLabel="缘散录" />;
  }

  return <CharacterDetailSwitch id={id} />;
}

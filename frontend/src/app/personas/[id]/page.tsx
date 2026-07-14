import { PersonaDetailClient } from "@/components/persona-library/PersonaDetailClient";

interface PersonaDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function PersonaDetailPage({ params }: PersonaDetailPageProps) {
  const { id } = await params;
  return <PersonaDetailClient personaId={id} />;
}

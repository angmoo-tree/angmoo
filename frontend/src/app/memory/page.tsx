import { MemoryWorkspace } from "@/features/memory/public";

type MemoryPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function MemoryPage({ searchParams }: MemoryPageProps) {
  const params = await searchParams;
  return (
    <MemoryWorkspace
      initialMemoryId={first(params.memory)}
      initialSubjectId={first(params.subject)}
      initialWorldId={first(params.world)}
    />
  );
}

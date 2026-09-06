"use client";
import type {ComponentProps} from 'react';
import {listAgents} from '@/features/characters/api/agents';
import {TreeCommunityClient} from '@/features/tree/components/tree-community-client';
export function TreeCommunityScreen(props: Omit<ComponentProps<typeof TreeCommunityClient>, 'loadRelatedCharacters'>) {return <TreeCommunityClient {...props} loadRelatedCharacters={listAgents} />;}

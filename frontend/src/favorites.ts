export type FavoriteEntityType =
  | "model"
  | "creator"
  | "franchise"
  | "series"
  | "collection"
  | "tag"

export interface FavoriteListSummary {
  id: number
  name: string
  item_count: number
  created_at: string
  updated_at: string
}

export interface FavoriteListItem {
  id: number
  entity_type: FavoriteEntityType
  label: string
  url: string | null
  is_available: boolean
  created_at: string
  model_id: number | null
  thumbnail_url: string | null
  artwork_url: string | null
  variant: string | null
  creator: string | null
  franchise: string | null
  series: string | null
  collection: string | null
  status: string | null
}

export interface FavoriteListDetail extends FavoriteListSummary {
  items: FavoriteListItem[]
}

export interface FavoriteTarget {
  key: string
  label: string
  entity_type: FavoriteEntityType
  model_id?: number
  tag_id?: number
  value?: string
}

export interface FavoriteMembershipList {
  id: number
  name: string
  item_id?: number
}

export interface FavoriteModelMembership {
  model_id: number
  lists: FavoriteMembershipList[]
}

interface FavoriteModelContext {
  id: number
  name: string
  variant: string | null
  creator: string | null
  franchise: string | null
  series: string | null
  collection: string | null
  tags: Array<{ id: number; name: string }>
}

export function favoriteTargetsForModel(model: FavoriteModelContext): FavoriteTarget[] {
  const targets: FavoriteTarget[] = [
    {
      key: `model:${model.id}`,
      label: `Model: ${model.name}${model.variant ? ` - ${model.variant}` : ""}`,
      entity_type: "model",
      model_id: model.id,
    },
  ]
  const textTargets: Array<[FavoriteEntityType, string | null]> = [
    ["creator", model.creator],
    ["franchise", model.franchise],
    ["series", model.series],
    ["collection", model.collection],
  ]
  for (const [entityType, value] of textTargets) {
    if (!value) continue
    targets.push({
      key: `${entityType}:${value}`,
      label: `${entityType[0].toUpperCase()}${entityType.slice(1)}: ${value}`,
      entity_type: entityType,
      value,
    })
  }
  for (const tag of model.tags) {
    targets.push({
      key: `tag:${tag.id}`,
      label: `Tag: ${tag.name}`,
      entity_type: "tag",
      tag_id: tag.id,
    })
  }
  return targets
}

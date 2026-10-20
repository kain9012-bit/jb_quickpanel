export type FavoriteKind = "style" | "form" | "kedufine_form" | "symbol" | "page";
export type CardFavorites = Record<FavoriteKind, string[]>;

export function cardFavoriteKey(item: { key: string; favorite_key?: string }): string {
  return item.favorite_key ?? item.key;
}

export function orderFavoriteCards<T extends { key: string; favorite_key?: string }>(items: T[], favorites: string[]): T[] {
  const ranks = new Map(favorites.map((key, index) => [key, index]));
  return [...items].sort((left, right) =>
    (ranks.get(cardFavoriteKey(left)) ?? favorites.length) - (ranks.get(cardFavoriteKey(right)) ?? favorites.length),
  );
}

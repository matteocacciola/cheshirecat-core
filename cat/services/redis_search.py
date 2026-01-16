import json
from typing import List
from redis import RedisError

from cat.auth.auth_utils import check_password
from cat.db.crud import get_db
import cat.db.cruds.users as crud_users
from cat.db.database import DEFAULT_AGENTS_KEY, DEFAULT_SYSTEM_KEY
from cat.log import log
from cat.utils import singleton


USERNAME_SEARCH_SCRIPT = f"""
local matches = {{}}
local cursor = "0"
local pattern = "{DEFAULT_AGENTS_KEY}:*:users"
local username = ARGV[1]

repeat
    local result = redis.call("SCAN", cursor, "MATCH", pattern, "COUNT", 100)
    cursor = result[1]
    local keys = result[2]

    for i, key in ipairs(keys) do
        local data = redis.call("JSON.GET", key)

        if data then
            local users_obj = cjson.decode(data)

            for user_id, user in pairs(users_obj) do
                if user.username == username then
                    local agent_name = string.match(key, "([^:]+):users$")

                    table.insert(matches, cjson.encode({{
                        user = user,
                        agent_name = agent_name,
                    }}))
                end
            end
        end
    end
until cursor == "0"

if #matches > 0 then
    return cjson.encode(matches)
end
return nil
"""


@singleton
class RedisSearchService:
    def __init__(self):
        self.redis_client = get_db()

    def search_user_by_credentials(self, username: str, password: str) -> List[str] | None:
        """
        Search for users by username across all agents and verify password.

        Args:
            username: Username to search for.
            password: Password to verify.

        Returns:
            List of matching users with agent metadata, or None if no matches found.

        Raises:
            RedisError: If Redis connection fails.
        """
        try:
            username_search_sha = self.redis_client.script_load(USERNAME_SEARCH_SCRIPT)

            # Phase 1: Find all users with this username across all agents
            result = self.redis_client.evalsha(username_search_sha, 0, username)

            # Phase 2: Find the user with the username and password within the "system" agent
            system_user = crud_users.get_user_by_credentials(DEFAULT_SYSTEM_KEY, username, password)

            if not result and not system_user:
                return None

            # Phase 2: Verify password for each candidate
            matches_raw = json.loads(result) if result else []
            if not matches_raw and not system_user:
                return None

            valid_matches = (
                [] if not system_user
                else [json.dumps({"agent_name": DEFAULT_SYSTEM_KEY, "user": system_user})]
            )
            for match_str in matches_raw:
                match = json.loads(match_str)
                stored_hash = match["user"]["password"]

                # Verify password with bcrypt
                if check_password(password, stored_hash):
                    valid_matches.append(match_str)

            return valid_matches
        except RedisError as e:
            log.error(f"Redis error searching for username {username}: {e}")
            return None


def get_redis_search_service() -> RedisSearchService:
    return RedisSearchService()

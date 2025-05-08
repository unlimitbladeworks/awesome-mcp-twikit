from fastmcp import FastMCP, Context
import twikit
import os
from pathlib import Path
import logging
from typing import Optional, List
import time
import traceback

# Create an MCP server
mcp = FastMCP("mcp-twikit-tools")
logger = logging.getLogger(__name__)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

USERNAME = os.getenv('TWITTER_USERNAME')
EMAIL = os.getenv('TWITTER_EMAIL')
PASSWORD = os.getenv('TWITTER_PASSWORD')
TOTP_SECRET = os.getenv('TWITTER_2FA')
COOKIES_PATH = Path.home() / '.mcp-twikit-tools' / 'cookies.json'

# Rate limit tracking
RATE_LIMITS = {}
RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes in seconds


async def get_twitter_client() -> twikit.Client:
    """Initialize and return an authenticated Twitter client."""
    client = twikit.Client('en-US')

    if COOKIES_PATH.exists():
        try:
            client.load_cookies(COOKIES_PATH)
            # 可以添加验证cookie是否有效的逻辑
        except Exception as e:
            logger.warning(f"无法加载cookie，将重新登录: {e}")
            await login_and_save_cookies(client)
    else:
        await login_and_save_cookies(client)

    return client


async def login_and_save_cookies(client):
    try:
        await client.login(
            auth_info_1=USERNAME,
            auth_info_2=EMAIL,
            password=PASSWORD,
            totp_secret=TOTP_SECRET
        )
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        client.save_cookies(COOKIES_PATH)
    except Exception:
        logger.error(f"登录失败:", traceback.print_exc())
        raise


def check_rate_limit(endpoint: str) -> bool:
    """Check if we're within rate limits for a given endpoint."""
    now = time.time()
    if endpoint not in RATE_LIMITS:
        RATE_LIMITS[endpoint] = []

    # Remove old timestamps
    RATE_LIMITS[endpoint] = [t for t in RATE_LIMITS[endpoint] if now - t < RATE_LIMIT_WINDOW]

    # Check limits based on endpoint
    if endpoint == 'tweet':
        return len(RATE_LIMITS[endpoint]) < 300  # 300 tweets per 15 minutes
    elif endpoint == 'dm':
        return len(RATE_LIMITS[endpoint]) < 1000  # 1000 DMs per 15 minutes
    return True


# Existing search and read tools
@mcp.tool()
async def search_twitter(query: str, sort_by: str = 'Top', count: int = 15, ctx: Context = None) -> str:
    """Search twitter with a query. Sort by 'Top' or 'Latest'"""
    try:
        client = await get_twitter_client()
        tweets = await client.search_tweet(query, product=sort_by, count=count)
        return convert_tweets_to_markdown(tweets)
    except Exception as e:
        logger.error(f"Failed to search tweets: {e}")
        return f"Failed to search tweets: {e}"


@mcp.tool()
async def get_user_tweets(username: str, tweet_type: str = 'Tweets', count: int = 15, ctx: Context = None) -> str:
    """Get tweets from a specific user's timeline."""
    try:
        client = await get_twitter_client()
        username = username.lstrip('@')
        user = await client.get_user_by_screen_name(username)
        if not user:
            return f"Could not find user {username}"

        tweets = await client.get_user_tweets(
            user_id=user.id,
            tweet_type=tweet_type,
            count=count
        )
        return convert_tweets_to_markdown(tweets)
    except Exception as e:
        logger.error(f"Failed to get user tweets: {e}")
        return f"Failed to get user tweets: {e}"


@mcp.tool()
async def get_timeline(count: int = 20) -> str:
    """Get tweets from your home timeline (For You)."""
    try:
        client = await get_twitter_client()
        tweets = await client.get_timeline(count=count)
        return convert_tweets_to_markdown(tweets)
    except Exception as e:
        logger.error(f"Failed to get timeline: {e}")
        return f"Failed to get timeline: {e}"


@mcp.tool()
async def get_latest_timeline(count: int = 20) -> str:
    """Get tweets from your home timeline (Following)."""
    try:
        client = await get_twitter_client()
        tweets = await client.get_latest_timeline(count=count)
        return convert_tweets_to_markdown(tweets)
    except Exception as e:
        logger.error(f"Failed to get latest timeline: {e}")
        return f"Failed to get latest timeline: {e}"


# New write tools
@mcp.tool()
async def post_tweet(
        text: str,
        media_paths: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None
) -> str:
    """Post a tweet with optional media, reply, and tags."""
    try:
        if not check_rate_limit('tweet'):
            return "Rate limit exceeded for tweets. Please wait before posting again."

        client = await get_twitter_client()

        # Handle tags by converting to mentions
        if tags:
            mentions = ' '.join(f"@{tag.lstrip('@')}" for tag in tags)
            text = f"""{text}
{mentions}"""

        # Upload media if provided
        media_ids = []
        if media_paths:
            for path in media_paths:
                media_id = await client.upload_media(path, wait_for_completion=True)
                media_ids.append(media_id)

        # Create the tweet
        tweet = await client.create_tweet(
            text=text,
            media_ids=media_ids if media_ids else None,
            reply_to=reply_to
        )
        RATE_LIMITS.setdefault('tweet', []).append(time.time())
        return f"Successfully posted tweet: {tweet.id}"
    except Exception as e:
        logger.error(f"Failed to post tweet: {e}")
        return f"Failed to post tweet: {e}"


@mcp.tool()
async def delete_tweet(tweet_id: str) -> str:
    """Delete a tweet by its ID."""
    try:
        client = await get_twitter_client()
        await client.delete_tweet(tweet_id)
        return f"Successfully deleted tweet {tweet_id}"
    except Exception as e:
        logger.error(f"Failed to delete tweet: {e}")
        return f"Failed to delete tweet: {e}"


@mcp.tool()
async def send_dm(user_id: str, message: str, media_path: Optional[str] = None) -> str:
    """Send a direct message to a user."""
    try:
        if not check_rate_limit('dm'):
            return "Rate limit exceeded for DMs. Please wait before sending again."

        client = await get_twitter_client()

        media_id = None
        if media_path:
            media_id = await client.upload_media(media_path, wait_for_completion=True)

        await client.send_dm(
            user_id=user_id,
            text=message,
            media_id=media_id
        )
        RATE_LIMITS.setdefault('dm', []).append(time.time())
        return f"Successfully sent DM to user {user_id}"
    except Exception as e:
        logger.error(f"Failed to send DM: {e}")
        return f"Failed to send DM: {e}"


@mcp.tool()
async def delete_dm(message_id: str) -> str:
    """Delete a direct message by its ID."""
    try:
        client = await get_twitter_client()
        await client.delete_dm(message_id)
        return f"Successfully deleted DM {message_id}"
    except Exception as e:
        logger.error(f"Failed to delete DM: {e}")
        return f"Failed to delete DM: {e}"


@mcp.tool()
async def get_tweet_thread(tweet_url: str, ctx: Context = None) -> str:
    """获取指定推文及其所有回复线程内容。
    
    参数:
        tweet_url: 推文的URL，格式如 https://x.com/username/status/123456789
    """
    try:
        client = await get_twitter_client()
        
        # 从URL中提取推文ID
        tweet_id = tweet_url.split('/status/')[1].split('?')[0]
        
        # 获取主推文
        main_tweet = await client.get_tweet_detail(tweet_id)
        if not main_tweet:
            return f"无法找到ID为 {tweet_id} 的推文"
        
        # 获取回复线程
        replies = await client.get_tweet_replies(tweet_id, count=50)
        
        # 将主推文和回复转换为markdown
        result = ["## 主推文"]
        result.append(convert_tweets_to_markdown([main_tweet]))
        
        if replies:
            result.append("\n## 回复线程")
            result.append(convert_tweets_to_markdown(replies))
        else:
            result.append("\n## 回复线程\n*没有回复*")
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"获取推文线程失败: {e}")
        return f"获取推文线程失败: {e}"


def convert_tweets_to_markdown(tweets) -> str:
    """Convert a list of tweets to markdown format."""
    result = []
    for tweet in tweets:
        result.append(f"### @{tweet.user.screen_name}")
        result.append(f"**{tweet.created_at}**")
        result.append(tweet.text)
        if hasattr(tweet, 'retweet_count') and hasattr(tweet, 'like_count'):
            result.append(f"♻️ {tweet.retweet_count} 🧡 {tweet.like_count}")
        if tweet.media:
            for media in tweet.media:
                result.append(f"![media]({media.url})")
        result.append("---")
    return "\n".join(result)


if __name__ == '__main__':
    import asyncio

    asyncio.run(get_user_tweets("test"))

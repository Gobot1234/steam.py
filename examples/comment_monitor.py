import re

import steam

client = steam.Client()

# Please make sure that you do NOT ever share these,
# you should be responsible for putting your own
# measures in place to make sure no one apart
# from you ever has access to these.

username = ''
password = ''
shared_secret = ''

URL_REGEX = re.compile(r'http[s]?://(?:\w|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
# this regex matches any valid website url


@client.event
async def on_ready():
    print('Ready')
    async for comment in client.user.comments():  # check our comments since we last logged in
        if comment.author in client.user.friends:  # ignore messages from friends
            return

        if URL_REGEX.search(comment.content) is not None:  # there is a url in the comment's content
            await comment.delete()  # delete the comment
            await comment.author.comment("Please don't post urls on my profile again.")
            # finally warn them about posting urls in your comments
            print('Deleted a suspicious comment containing a url from', comment.author.name)


@client.event
async def on_comment(comment):
    print(f'Received comment #{comment.id}, from', comment.author.name)
    if comment.owner != client.user:  # if we don't own the section, don't watch the comments
        print("We don't monitor comments here")
        return

    if comment.author in client.user.friends:  # ignore messages from friends
        print('Ignoring as they are a friend')
        return

    if URL_REGEX.search(comment.content) is not None:  # there is a url in the comment's content
        await comment.delete()  # delete the comment
        await comment.author.comment("Please don't post urls on my profile again.")
        print('Deleted a suspicious comment containing a url from', comment.author.name)
        # finally warn them about posting urls in your comments


client.run(username, password, shared_secret=shared_secret)

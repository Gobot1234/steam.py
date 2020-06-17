import steam

client = steam.Client()


@client.event
async def on_ready():
    print('Ready')
    async for comment in client.user.comments():  # check our comments since we last logged in
        if comment.author in client.user.friends:  # ignore messages from friends
            return

        if 'https://' in comment.content:  # there is a url in the comment's content
            await comment.delete()  # delete the comment
            await comment.author.comment("Please don't post urls on my profile again.")
            # finally warn them about posting urls in your comments
            print('Deleted a suspicious comment containing a url from', comment.author)


@client.event
async def on_comment(comment):
    print(f'Received comment #{comment.id}, from', comment.author)
    if comment.owner != client.user:  # if we don't own the section, don't watch the comments
        return

    if comment.author in client.user.friends:  # ignore messages from friends
        return

    if 'https://' in comment.content:
        await comment.delete()  # delete the comment
        await comment.author.comment("Please don't post urls on my profile again.")
        print('Deleted a suspicious comment containing a url from', comment.author)
        # finally warn them about posting urls in your comments


client.run('username', 'password')

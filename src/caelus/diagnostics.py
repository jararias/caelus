
import pylab as pl

from .skytype import SkyType


def density_ktk(data, sky_type):

    required = ['sza', 'eth', 'ghi', 'dif']
    if missing := list(set(required).difference(data.columns)):
        raise ValueError(f'missing required variables: {", ".join(missing)}')

    df = data.eval(
        '''
        KT = ghi / eth
        K = dif / ghi
        '''
    ).query('(sza < 85) & (ghi >= dif) & (ghi > 0)').dropna()[['KT', 'K']]

    fig, axes = pl.subplots(2, 3, constrained_layout=True)
    kwargs = dict(mincnt=1, norm=pl.cm.colors.LogNorm())

    for k, sky_t in enumerate(SkyType.skip_unknown()):
        ax = axes[k // 3, k % 3]

        sky_name = "".join(map(str.capitalize, sky_t.name.split('_')))
        if sky_name == 'CloudEnhancement':
            sky_name = 'CloudEn'

        ax.hexbin('KT', 'K', data=df, cmap='Greys', **kwargs)

        domain = sky_type == sky_t
        ax.hexbin('KT', 'K', data=df.loc[domain], cmap='jet', **kwargs)
        ax.set(xlabel='K$_T$', ylabel='K', title=sky_name)
        ax.axis([0, 1.21, 0, 1.01])

    fig.tight_layout()
    return fig


def histogram(sky_type):

    colors = ['#80008080', '#0000ff80', '#1e90ff80',
              '#00ffff80', '#ffa50080', '#ff000080']

    known_skies = sky_type != SkyType.UNKNOWN
    counts = sky_type.loc[known_skies].value_counts().sort_index()

    sky_type_names = [
        "".join(map(str.capitalize, SkyType(sky_type_value).name.split('_')))
        for sky_type_value in counts.index]
    sky_type_names[sky_type_names.index('CloudEnhancement')] = 'CloudEn'
    counts.index = sky_type_names

    counts.divide(counts.sum()).mul(100).plot(
        kind='bar', rot=25, ax=pl.gca(), fontsize=12,
        width=0.8, color=colors, zorder=1000)

    pl.grid(which='major', axis='y', lw=0.2, color='0.2', dashes=(10, 5), zorder=-1000)
    pl.ylabel('Sky type frequency (%)')
    pl.ylim(0, None)
    pl.tight_layout()


def pie_chart(sky_type):

    colors = ['#80008080', '#0000ff80', '#1e90ff80',
              '#00ffff80', '#ffa50080', '#ff000080']

    known_skies = sky_type != SkyType.UNKNOWN
    counts = sky_type.loc[known_skies].value_counts().sort_index()

    sky_type_names = [
        "".join(map(str.capitalize, SkyType(sky_type_value).name.split('_')))
        for sky_type_value in counts.index]
    sky_type_names[sky_type_names.index('CloudEnhancement')] = 'CloudEn'
    counts.index = sky_type_names

    patches, _ = pl.pie(
        counts.divide(counts.sum()).mul(100).values, colors=colors,
        wedgeprops=dict(edgecolor='w', linewidth=0.3))
    pl.gca().axis('equal')

    pl.legend(patches, sky_type_names, ncol=1, loc='upper left',
              bbox_to_anchor=(0., 1.), frameon=False)
    pl.tight_layout()

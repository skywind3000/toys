#ifndef ANCHORLAYOUT_H
#define ANCHORLAYOUT_H

#include <QWidget>

//anchor:[left],[right],[top],[bottom]
//dock:left/right/top/bottom/fill

class AnchorLayout
{
public:
    AnchorLayout(QWidget *root);
    int init(void);
    int update(void);
private:
    struct anchors
    {
        bool left=false;
        bool right=false;
        bool top=false;
        bool bottom=false;

        bool inUse(void)
        {
            if(left)
                return true;
            if(right)
                return true;
            if(top)
                return true;
            if(bottom)
                return true;
            return false;
        }
    };
    QWidget *root=NULL;
    QString anchor_name;
    QString dock_name;

    anchors __anchor_parse(QString anchor);
    bool __need_recursion (QWidget *root);//, bool store=true);
    int __geometry_store (QWidget *root);
    QRect __get_origin_geometry (QWidget *widget);
    int __geometry_update (QWidget *root);
    bool __layout_anchor (QWidget *widget, anchors anchor, int dx, int dy);
    bool __layout_docking (QWidget *widget, QRect client, QString dock);
    bool __move_widget (QWidget *widget, QRect rect);

};

#endif // ANCHORLAYOUT_H

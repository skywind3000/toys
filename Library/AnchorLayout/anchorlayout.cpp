#include "anchorlayout.h"
#include <QVariant>

AnchorLayout::AnchorLayout(QWidget *root)
{
    this->root=root;
    this->anchor_name="anchor";
    this->dock_name="dock";
}

int AnchorLayout::init(void)
{
    this->__geometry_store(this->root);
    return 0;
}

int AnchorLayout::update(void)
{
    this->__geometry_update(this->root);
    return 0;
}

AnchorLayout::anchors AnchorLayout::__anchor_parse(QString anchor)
{
    AnchorLayout::anchors retval;
    if(anchor.isEmpty())
        return retval;
    QStringList strs=  anchor.split(",");

    foreach (QString s, strs)
    {
        if(s == QString::fromLocal8Bit("left"))
        {
            retval.left=true;
        }
        else if(s == QString::fromLocal8Bit("right"))
        {
            retval.right=true;
        }
        else if(s == QString::fromLocal8Bit("top"))
        {
            retval.top=true;
        }
        else if(s == QString::fromLocal8Bit("bottom"))
        {
            retval.bottom=true;
        }
    }

    return retval;
}

bool AnchorLayout::__need_recursion (QWidget *root)//, bool store)
{
    if(NULL != root)
        return true;
    QString anchor=root->property(this->anchor_name.toLocal8Bit().constData()).toString();
    if(!anchor.isEmpty())
        return true;
    QString docking=root->property(this->dock_name.toLocal8Bit().constData()).toString();
    if(!docking.isEmpty())
        return true;
    return false;
}

int AnchorLayout::__geometry_store (QWidget *root)
{
    QRect geometry = root->geometry();
    if(!geometry.isValid())
        return -1;
    root->setProperty("__layout_origin", geometry);
    foreach (QObject *widget, root->children())
    {
        if(!widget->inherits("QWidget"))
            continue;
        if(!this->__need_recursion(qobject_cast<QWidget*>(widget)))//,true))
            continue;
        this->__geometry_store(qobject_cast<QWidget*>(widget));
    }
    return 0;
}

QRect AnchorLayout::__get_origin_geometry (QWidget *widget)
{
    QRect origin = widget->property("__layout_origin").toRect();
    if(origin.isNull())
    {
        origin = widget->geometry();
        widget->setProperty("__layout_origin", origin);
    }
    //qDebug("(%d,%d,%d,%d)", origin.x(),origin.y(),origin.width(),origin.height());
    return origin;
}

int AnchorLayout::__geometry_update (QWidget *root)
{
    if(!root->inherits("QWidget"))
        return -1;
    else if(!root->size().isValid())
        return -2;
    QRect origin = this->__get_origin_geometry(root);
    QRect client = root->geometry();
    int dx = client.width() - origin.width();
    int dy = client.height() - origin.height();
    QRect avail = root->geometry();
    avail.moveTo(0, 0);
    foreach (QObject *widget, root->children())
    {
        if(!widget->inherits("QWidget"))
            continue;
        QString anchor_str = widget->property(this->anchor_name.toLocal8Bit().constData()).toString();
        QString dock_str = widget->property(this->dock_name.toLocal8Bit().constData()).toString();
        AnchorLayout::anchors anchor = this->__anchor_parse(anchor_str);
        dock_str=dock_str.trimmed().toLower();
        if(anchor.inUse())
        {
            if(dock_str.isEmpty())
                this->__layout_anchor(qobject_cast<QWidget*>(widget),anchor,dx,dy);
        }
        if(!dock_str.isEmpty())
        {
            if(client.isValid())
                this->__layout_docking(qobject_cast<QWidget*>(widget),avail,dock_str);
        }
        this->__geometry_update(qobject_cast<QWidget*>(widget));
    }
    return 0;
}

bool AnchorLayout::__layout_anchor (QWidget *widget, AnchorLayout::anchors anchor, int dx, int dy)
{
    QRect rc = this->__get_origin_geometry(widget);
    if(anchor.left)
    {
        if(anchor.right)
            rc.setWidth(rc.width()+dx);
    }
    else
    {
        if(anchor.right)
            rc.moveTo(rc.left() + dx, rc.top());
        else
            rc.moveTo(rc.left() + dx / 2, rc.top());
    }
    if(anchor.top)
    {
        if(anchor.bottom)
            rc.setHeight(rc.height() + dy);
    }
    else
    {
        if(anchor.bottom)
            rc.moveTo(rc.left(), rc.top() + dy);
        else
            rc.moveTo(rc.left(), rc.top() + dy / 2);
    }
    //qDebug("%s:(%d,%d,%d,%d)", widget->objectName().toLocal8Bit().constData(),rc.x(),rc.y(),rc.width(),rc.height());
    widget->setGeometry(rc);
    return true;
}

bool AnchorLayout::__layout_docking (QWidget *widget, QRect client, QString dock)
{
    QRect rc = widget->frameGeometry();
    if (!rc.isValid())
        return false;
    else if(!client.isValid())
        return false;
    if(dock == QString::fromLocal8Bit("left"))
    {
        rc.moveTo(client.x(), client.y());
        rc.setHeight(client.height());
        client.setLeft(client.left() + rc.width());
    }
    else if(dock == QString::fromLocal8Bit("right"))
    {
        rc.moveTo(client.right() - rc.width(), client.y());
        rc.setHeight(client.height());
        client.setRight(client.right() - rc.width());
    }
    else if(dock == QString::fromLocal8Bit("top"))
    {
        rc.moveTo(client.x(), client.y());
        rc.setWidth(client.width());
        client.setTop(client.top() + rc.height());
    }
    else if(dock == QString::fromLocal8Bit("bottom"))
    {
        rc.moveTo(client.x(), client.height() - rc.height());
        rc.setWidth(client.width());
        client.setBottom(client.bottom() - rc.height());
    }
    else if((dock == QString::fromLocal8Bit("fill"))||(dock == QString::fromLocal8Bit("client")))
    {
        rc.setRect(client.x(), client.y(), client.width(), client.height());
    }
    else
        return false;
    this->__move_widget(widget, rc);
    return true;
}

bool AnchorLayout::__move_widget (QWidget *widget, QRect rect)
{
    QRect bound = widget->frameGeometry();
    QRect client = widget->geometry();
    int ox = client.x() - bound.x();
    int oy = client.y() - bound.y();
    int dx = bound.width() - client.width();
    int dy = bound.height() - client.height();
    widget->setGeometry(rect.x() + ox, rect.y() + oy,
            rect.width() - dx, rect.height() - dy);
    return true;
}
